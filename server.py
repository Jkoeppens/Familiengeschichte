#!/usr/bin/env python3
"""
server.py — Minimaler Flask-API-Server für familiengeschichte.db.

Endpoints:
  GET /api/persons
  GET /api/person/<person_id>/weg
  GET /api/person/<person_id>/biografie    ← _DATA_BIOGRAFIE-kompatibles Format
"""

import json
import calendar
from pathlib import Path
from flask import Flask, jsonify, send_from_directory

import db

ROOT = Path(__file__).parent

app = Flask(__name__)


@app.route('/')
@app.route('/<path:filename>')
def static_files(filename='person_karte.html'):
    """Serviert HTML/CSS/JS aus dem Projektverzeichnis."""
    return send_from_directory(ROOT, filename)


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
                    inferred.append({
                        'type':         ev.get('type'),
                        'datum':        monat,
                        'ort':          place.get('name'),
                        'lat':          lat,
                        'lon':          lon,
                        'certainty':    src.get('certainty'),
                        'einheit':      ev.get('einheit_original'),
                        'inferred':     True,
                        'generated_by': src.get('generated_by'),
                        'via_unit':     ev.get('_via_unit'),
                        'inferred_unit': ev.get('_inferred_unit_id'),
                        'note':         src.get('note'),
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
    app.run(port=5050, debug=True, use_reloader=False)
