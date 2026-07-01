#!/usr/bin/env python3
"""
server.py — Minimaler Flask-API-Server für familiengeschichte.db.

Endpoints:
  GET  /api/persons
  GET  /api/person/<person_id>/weg
  GET  /api/person/<person_id>/biografie
  POST /api/upload
  GET  /api/upload/<job_id>/status
"""

import json
import calendar
import os
import secrets
import shutil
import tempfile
import threading
import uuid
from pathlib import Path
from flask import Flask, jsonify, redirect, request, send_from_directory, session, url_for

import db
from pipeline_b import classify_pdf, ingest_bundesarchiv, ingest_wast

ROOT     = Path(__file__).parent
DATA_DIR = Path(os.environ.get('DATA_DIR', ROOT))

# Große Datendateien die auf Railway im Volume liegen (DATA_DIR),
# lokal aber neben dem Code liegen (ROOT = DATA_DIR per Default).
_DATA_FILES = {
    'familiengeschichte.db',
    'stanford_borders_hires.pmtiles',
    'kz_lager.geojson',
    'ghettos_new.json',
    'operationen_wk2_new.json',
    'yahad_killing_sites_new.json',
    'gazeteer_cache.json',
}

app = Flask(__name__)

# ── Startup-Check: Pflicht-Datendateien im DATA_DIR vorhanden? ────────────────
_REQUIRED_DATA = {
    'familiengeschichte.db',
    'stanford_borders_hires.pmtiles',
    'kz_lager.geojson',
    'ghettos_new.json',
    'operationen_wk2_new.json',
    'yahad_killing_sites_new.json',
}
_missing_files = sorted(f for f in _REQUIRED_DATA if not (DATA_DIR / f).exists())
if _missing_files:
    print(f"WARNUNG: Datendateien fehlen in DATA_DIR={DATA_DIR}: {_missing_files}", flush=True)

# ── Sicherheits-Konfiguration ─────────────────────────────────────────────────
# WICHTIG: debug=False muss bei jedem öffentlichen Zugriff (ngrok o.ä.) gesetzt
# bleiben. debug=True würde den interaktiven Werkzeug-Debugger freigeben, der
# beliebige Python-Code-Ausführung im Browser erlaubt.
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB gesamt pro Request

_APP_PASSWORD   = os.getenv('APP_PASSWORD')      # optional; wenn leer → kein Login
_SECRET_KEY     = os.getenv('FLASK_SECRET_KEY') or secrets.token_hex(32)
app.secret_key  = _SECRET_KEY

ALLOWED_EXTENSIONS = {'.html', '.json', '.geojson', '.pmtiles', '.js', '.css'}

# ── Passwortschutz (nur aktiv wenn APP_PASSWORD gesetzt) ──────────────────────

_LOGIN_HTML = """\
<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">
<title>Login</title>
<style>
  body { margin: 0; display: flex; align-items: center; justify-content: center;
         min-height: 100vh; background: #0f0f1a; font-family: system-ui, sans-serif; }
  form { background: #1a1a2e; border: 1px solid rgba(255,255,255,.15); border-radius: 10px;
         padding: 32px 28px; width: 280px; }
  h2   { margin: 0 0 20px; color: #e2e8f0; font-size: 15px; font-weight: 600; }
  input[type=password] { width: 100%; box-sizing: border-box; background: rgba(255,255,255,.08);
         border: 1px solid rgba(255,255,255,.2); border-radius: 4px; color: #fff;
         padding: 7px 9px; font-size: 13px; margin-bottom: 12px; }
  button { width: 100%; background: #2b4c7e; border: none; border-radius: 5px;
           color: #e2e8f0; font-size: 13px; padding: 8px; cursor: pointer; }
  button:hover { background: #3a6198; }
  .err { color: #fc8181; font-size: 11px; margin-bottom: 10px; }
</style></head><body>
<form method="post">
  <h2>Familiengeschichte</h2>
  {error}
  <input type="password" name="password" placeholder="Passwort" autofocus>
  <button type="submit">Anmelden</button>
</form></body></html>"""


@app.route('/_login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == _APP_PASSWORD:
            session['auth'] = True
            return redirect(request.args.get('next') or '/')
        error = '<p class="err">Falsches Passwort.</p>'
    else:
        error = ''
    return _LOGIN_HTML.replace('{error}', error), 200


@app.route('/health')
def health():
    if _missing_files:
        return jsonify({'status': 'degraded', 'missing': _missing_files}), 200
    return jsonify({'status': 'ok'}), 200


@app.before_request
def check_data_files():
    """503 auf allen Endpoints solange Pflicht-Datendateien fehlen — außer / und /health."""
    if not _missing_files:
        return
    if request.endpoint in ('health', 'static_files'):
        return
    return jsonify({
        'error': 'Datendateien fehlen im Volume. Bitte /data befüllen.',
        'missing': _missing_files,
    }), 503


@app.before_request
def require_auth():
    if not _APP_PASSWORD:
        return  # Passwortschutz deaktiviert
    if request.endpoint in ('login', 'health'):
        return  # Login-Seite und Healthcheck immer erreichbar
    if not session.get('auth'):
        return redirect(url_for('login', next=request.path))

# ── Upload-Job-Verwaltung ──────────────────────────────────────────────────────

_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()


def _set_job(job_id: str, **kw) -> None:
    with _JOBS_LOCK:
        _JOBS[job_id].update(kw)


def _merge_actor(secondary_id: str, primary_id: str) -> None:
    """Hängt alle Participations von secondary auf primary um, löscht secondary."""
    with db._get_conn() as conn:
        rows = conn.execute(
            "SELECT event_id, relation, role, data FROM participations WHERE actor_id=?",
            (secondary_id,),
        ).fetchall()
        for r in rows:
            payload = json.loads(r["data"])
            payload["actor_id"] = primary_id
            conn.execute(
                "INSERT OR REPLACE INTO participations "
                "(event_id, actor_id, relation, role, data) VALUES (?,?,?,?,?)",
                (r["event_id"], primary_id, r["relation"], r["role"],
                 json.dumps(payload, ensure_ascii=False)),
            )
        conn.execute("DELETE FROM participations WHERE actor_id=?", (secondary_id,))
        conn.execute("DELETE FROM actors WHERE id=?", (secondary_id,))
        conn.commit()


def _run_job(job_id: str, file_paths: list[Path], tmpdir: Path) -> None:
    try:
        _set_job(job_id, step="Dokumente werden gelesen")

        all_actor_ids: list[str] = []

        for path in file_paths:
            typ, _conf = classify_pdf(path)

            if typ == "unbekannt":
                _set_job(job_id, status="error",
                         message=f"Unbekannter Dokumenttyp: {path.name}")
                return

            if typ == "wast_karteikarte":
                _set_job(job_id, step="WASt-Karte wird ausgelesen")
                ids = ingest_wast(path)
            else:  # bundesarchiv_auskunft
                _set_job(job_id, step="Einheiten werden zugeordnet")
                ids = ingest_bundesarchiv(path)

            all_actor_ids.extend(ids)

        unique_ids = list(dict.fromkeys(i for i in all_actor_ids if i))

        if not unique_ids:
            _set_job(job_id, status="error",
                     message="Aus den hochgeladenen Dokumenten konnte keine Person "
                             "extrahiert werden")
            return

        with db._get_conn() as conn:
            persons = []
            for actor_id in unique_ids:
                row = conn.execute(
                    "SELECT pref_label FROM actors WHERE id=?", (actor_id,)
                ).fetchone()
                persons.append({
                    "person_id": actor_id,
                    "name": row["pref_label"] if row else actor_id,
                })

        _set_job(job_id, status="done", step="Fertig", persons=persons)

    except Exception as exc:
        _set_job(job_id, status="error", message=str(exc))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── POST /api/upload ──────────────────────────────────────────────────────────

@app.route('/api/upload', methods=['POST'])
def upload():
    files = request.files.getlist('files[]')
    if not files or all(f.filename == '' for f in files):
        return jsonify({'error': 'Keine Dateien übermittelt'}), 400
    if len(files) > 10:
        return jsonify({'error': 'Maximal 10 Dateien pro Upload erlaubt'}), 400

    tmpdir = Path(tempfile.mkdtemp())
    paths: list[Path] = []
    for f in files:
        dest = tmpdir / f"{uuid.uuid4().hex}.pdf"
        f.save(str(dest))
        paths.append(dest)

    job_id = uuid.uuid4().hex[:8]
    with _JOBS_LOCK:
        _JOBS[job_id] = {
            'status':  'running',
            'step':    'Dokumente werden gelesen',
            'persons': [],
            'message': None,
        }

    t = threading.Thread(target=_run_job, args=(job_id, paths, tmpdir), daemon=True)
    t.start()

    return jsonify({'job_id': job_id})


# ── GET /api/upload/<job_id>/status ───────────────────────────────────────────

@app.route('/api/upload/<job_id>/status')
def upload_status(job_id):
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        return jsonify({'error': 'Job nicht gefunden'}), 404
    return jsonify(job)


@app.route('/')
@app.route('/<path:filename>')
def static_files(filename='person_karte.html'):
    """Serviert statische Dateien — nur erlaubte Endungen, kein Path-Traversal."""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return '', 404
    # Datendateien aus DATA_DIR (auf Railway: Volume), Quellcode-Assets aus ROOT
    base = DATA_DIR if filename in _DATA_FILES else ROOT
    target = (base / filename).resolve()
    if not str(target).startswith(str(base.resolve())):
        return '', 404
    return send_from_directory(base, filename)


# Event-Typ → WASt-Karteikarten-Typ (für die Karte)
_TYP_MAP = {
    'Wounding':       'verwundung',
    'Hospitalization': 'lazarett',
    'Discharge':      'entlassung',
    'Missing':        'vermisst',
}


# ── /api/persons ──────────────────────────────────────────────────────────────

@app.route('/api/persons')
def list_persons():
    """Alle Personen in der DB."""
    with db._get_conn() as conn:
        rows = conn.execute(
            "SELECT id, pref_label FROM actors WHERE type='Person'"
        ).fetchall()
    return jsonify([{'id': r['id'], 'name': r['pref_label']} for r in rows])


# ── /api/person/<id>/weg ──────────────────────────────────────────────────────

@app.route('/api/person/<person_id>/weg')
def get_weg(person_id):
    """Verortete Events der Person: direkte Koordinaten + verorte()-Lücken."""
    # ── Schritt 1: direkte Events mit Koordinaten ──────────────────────────
    with db._get_conn() as conn:
        rows = conn.execute(
            """
            SELECT e.type, e.time_begin, e.lat, e.lon, e.data
            FROM events e
            JOIN participations p ON p.event_id = e.id
            WHERE p.actor_id = ?
              AND e.lat IS NOT NULL
            ORDER BY e.time_begin
            """,
            (person_id,),
        ).fetchall()

        joining_dates = conn.execute(
            """
            SELECT json_extract(e.data,'$.time_span.begin')
            FROM events e
            JOIN participations p ON p.event_id = e.id
            WHERE p.actor_id = ?
              AND json_extract(e.data,'$.type') = 'PersonJoining'
              AND json_extract(e.data,'$.time_span.begin') IS NOT NULL
            ORDER BY json_extract(e.data,'$.time_span.begin')
            """,
            (person_id,),
        ).fetchall()

    result = []
    direct_months = set()
    for r in rows:
        data  = json.loads(r['data'])
        datum = data.get('time_span', {}).get('begin')
        if datum:
            direct_months.add(datum[:7])
        result.append({
            'type':      r['type'],
            'datum':     datum,
            'ort':       (data.get('place') or {}).get('name'),
            'lat':       r['lat'],
            'lon':       r['lon'],
            'certainty': (data.get('source') or {}).get('certainty'),
            'einheit':   data.get('einheit_original'),
            'inferred':  False,
        })

    # ── Schritt 2: Lücken mit verorte() füllen ────────────────────────────
    datums = [r['datum'] for r in result if r['datum']]
    def _to_ym(s: str, last: bool = False) -> str:
        """'1939' → '1939-01' (first) oder '1939-12' (last), '1943-08' bleibt."""
        s = s[:7]
        if len(s) == 4:
            return s + ('-12' if last else '-01')
        return s

    if joining_dates:
        first_ym = _to_ym(joining_dates[0][0])
        last_ym  = _to_ym(joining_dates[-1][0], last=True)
    else:
        first_ym = _to_ym(datums[0]) if datums else None
        last_ym  = _to_ym(datums[-1], last=True) if datums else None

    if not first_ym:
        return jsonify(result)

    def _unit_info(conn, unit_id):
        if not unit_id:
            return None
        row = conn.execute(
            """SELECT json_extract(a.data,'$.pref_label'),
                      json_extract(a.data,'$.tessin_band'),
                      json_extract(a.data,'$.tessin_seite'),
                      json_extract(a.data,'$._raw_text')
               FROM actors a WHERE a.id = ?""",
            (unit_id,),
        ).fetchone()
        if not row:
            return None
        band, seite = row[1], row[2]
        return {
            'id':           unit_id,
            'pref_label':   row[0],
            'tessin_band':  band,
            'tessin_seite': seite,
            'tessin_ref':   f'Tessin Bd. {band}, S. {seite}' if band and seite else None,
            'raw_text':     row[3],
        }

    # Alle Monate zwischen erstem und letztem direkten Punkt
    y, m = int(first_ym[:4]), int(first_ym[5:7])
    y1, m1 = int(last_ym[:4]), int(last_ym[5:7])
    inferred = []
    while (y, m) <= (y1, m1):
        monat = f"{y:04d}-{m:02d}"
        if monat not in direct_months:
            for ev in db.verorte(person_id, monat):
                place = ev.get('place') or {}
                lat, lon = place.get('lat'), place.get('lon')
                if lat and lon:
                    src = ev.get('source') or {}
                    via_id      = ev.get('_via_unit')
                    inferred_id = ev.get('_inferred_unit_id')
                    with db._get_conn() as conn:
                        via_info      = _unit_info(conn, via_id)
                        inferred_info = _unit_info(conn, inferred_id)
                    inferred.append({
                        'type':           ev.get('type'),
                        'datum':          monat,
                        'ort':            place.get('name'),
                        'lat':            lat,
                        'lon':            lon,
                        'certainty':      src.get('certainty'),
                        'einheit':        ev.get('einheit_original'),
                        'inferred':       True,
                        'generated_by':   src.get('generated_by'),
                        'via_unit':       via_id,
                        'inferred_unit':  inferred_id,
                        'note':           src.get('note'),
                        'via_unit_info':      via_info,
                        'inferred_unit_info': inferred_info,
                    })
                    break  # verorte() liefert nach certainty DESC — ersten nehmen
        m += 1
        if m > 12:
            m, y = 1, y + 1

    result = sorted(result + inferred, key=lambda x: x['datum'] or '')
    return jsonify(result)


# ── /api/person/<id>/biografie ────────────────────────────────────────────────

@app.route('/api/person/<person_id>/biografie')
def get_biografie(person_id):
    """
    Gibt _DATA_BIOGRAFIE-kompatibles Objekt zurück:
      { person, wast_ereignisse, einheitsmeldungen, dienstgrad }
    """
    with db._get_conn() as conn:
        actor_row = conn.execute(
            "SELECT data FROM actors WHERE id=?", (person_id,)
        ).fetchone()
        if not actor_row:
            return jsonify({'error': 'Person nicht gefunden'}), 404

        actor_data = json.loads(actor_row['data'])

        rows = conn.execute(
            """
            SELECT e.type, e.time_begin, e.time_end, e.lat, e.lon, e.data,
                   json_extract(e.data,'$.source.type') AS src_type
            FROM events e
            JOIN participations p ON p.event_id = e.id
            WHERE p.actor_id = ?
            ORDER BY e.time_begin
            """,
            (person_id,),
        ).fetchall()

    wast_ereignisse = []
    einheitsmeldungen = []

    for r in rows:
        data     = json.loads(r['data'])
        ts       = data.get('time_span', {})
        source   = data.get('source', {})
        place    = data.get('place') or {}
        src_type = r['src_type']

        # WASt Medical Events → wast_ereignisse
        if src_type == 'wast' and r['type'] in _TYP_MAP:
            wast_ereignisse.append({
                'quelle':    f"WASt {source.get('reference', '')}",
                'typ':       _TYP_MAP[r['type']],
                'datum':     ts.get('begin'),
                'datum_von': ts.get('begin'),
                'datum_bis': ts.get('end'),
                'ort':       place.get('name'),
                'lat':       r['lat'],
                'lon':       r['lon'],
                'einheit':   data.get('einheit_original'),
                'beleg':     data.get('label', '')[:120],
                'diagnose':  data.get('subtype'),
                'anmerkung': None,
            })

        # Bundesarchiv PersonJoining → einheitsmeldungen
        elif src_type == 'bundesarchiv' and r['type'] == 'PersonJoining':
            begin = ts.get('begin', '')
            year  = int(begin[:4]) if begin and begin[:4].isdigit() else None
            label = data.get('label', '')
            # Label-Format: "Name bei Einheit" → Einheitsname extrahieren
            bei_idx = label.find(' bei ')
            einheit = label[bei_idx + 5:] if bei_idx >= 0 else label
            einheitsmeldungen.append({
                'quelle':     f"Bundesarchiv {source.get('reference', '')}",
                'einheit':    einheit,
                'signatur':   source.get('reference'),
                'jahr':       year,
                'ort_bekannt': r['lat'] is not None,
                'ort':        place.get('name'),
                'lat':        r['lat'],
                'lon':        r['lon'],
                'anmerkung':  data.get('notes'),
            })

    person = {
        'name':       actor_data.get('pref_label', ''),
        'geboren':    actor_data.get('birth_date'),
        'geburtsort': None,
    }

    return jsonify({
        'person':            person,
        'wast_ereignisse':   wast_ereignisse,
        'einheitsmeldungen': einheitsmeldungen,
        'dienstgrad':        [],
    })


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    # debug=False ist Pflicht bei öffentlichem Zugriff (ngrok o.ä.) —
    # debug=True gibt den Werkzeug-Debugger frei, der beliebigen Code ausführt.
    port = int(os.environ.get('PORT', 5050))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
