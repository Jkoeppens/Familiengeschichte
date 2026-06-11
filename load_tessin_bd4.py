#!/usr/bin/env python3
"""
load_tessin_bd4.py
Konvertiert tessin_bd4_final.json → familiengeschichte.db
Erzeugt Actors (MilitaryUnit), UnitJoining-Events und Participations.
"""

import json
import re
import sys
import calendar
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))
import db

# ─── Konfiguration ─────────────────────────────────────────────────────────────

BAND     = 4
INPUT    = Path("tessin_bd4_final.json")
CREATED  = "2026-06-11"

# Mappt (nummer, einheit_exact) auf bekannte Actor-IDs aus actors.json
KNOWN_ACTOR_IDS: dict[tuple, str] = {
    ('20', 'Infanterie-Division (mot.)'): 'unit_20_pz_gren_div',
    ('20', 'Panzer-Division'):            'unit_20_pz_div',
}

# ─── ID-Normalisierung ──────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    s = s.lower()
    for a, b in [('ä','ae'),('ö','oe'),('ü','ue'),('ß','ss')]:
        s = s.replace(a, b)
    s = re.sub(r'[^a-z0-9]+', '_', s)
    return re.sub(r'_+', '_', s).strip('_')

def make_actor_id(nummer: str, einheit: str) -> str:
    key = (nummer.strip(), einheit.strip())
    if key in KNOWN_ACTOR_IDS:
        return KNOWN_ACTOR_IDS[key]
    return f"unit_{_norm(nummer)}_{_norm(einheit)}" if nummer.strip() else f"unit_{_norm(einheit)}"

def make_event_id(actor_id: str, jahr: int, m_begin: int, counter: int = 0) -> str:
    suffix = f"{actor_id.removeprefix('unit_')}_{jahr}_{m_begin:02d}"
    if counter:
        suffix += f"_{counter}"
    return f"event_unitjoining_{suffix}"

# ─── Actor-Felder ───────────────────────────────────────────────────────────────

def clean_heimatgarnison(raw: str) -> str | None:
    s = re.sub(r'^\d+\s*', '', raw.strip()).strip()
    return s or None

def derive_branch(einheit: str) -> str:
    low = einheit.lower()
    if re.search(r'\bss[-\s.]', low) or 'waffen-ss' in low or 'waffen-gren.div.d.ss' in low:
        return 'Waffen-SS'
    if ('luftwaffe' in low or re.search(r'\blw[.\s]', low)
            or re.search(r'\(l\)', low) or 'fallsch' in low or 'feld-div.' in low):
        return 'Luftwaffe'
    if 'kriegsmarine' in low or re.search(r'\bmarine\b', low):
        return 'Kriegsmarine'
    if 'ordnungspolizei' in low:
        return 'Ordnungspolizei'
    if 'einsatzgruppe' in low:
        return 'Einsatzgruppe'
    return 'Heer'

def derive_unit_type(einheit: str) -> str:
    low = einheit.lower()
    if 'heeresgruppe' in low:
        return 'Heeresgruppe'
    if (re.search(r'armeekorps', low) or re.search(r'armee-korps', low)
            or re.search(r'generalkommando', low) or re.search(r'\bkorps\b', low)):
        return 'Korps'
    if re.search(r'\barmee\b', low) and 'gruppe' not in low and 'korps' not in low:
        return 'Armee'
    if 'division' in low or re.search(r'\bdiv\.', low) or re.search(r'\bdiv\b', low):
        return 'Division'
    if 'regiment' in low or re.search(r'\brgt\.', low) or re.search(r'\brgt\b', low):
        return 'Regiment'
    if 'bataillon' in low or re.search(r'\bbtl\.', low) or re.search(r'\bbtl\b', low):
        return 'Bataillon'
    if 'kompanie' in low or re.search(r'\bkp\.', low) or re.search(r'\bkp\b', low):
        return 'Kompanie'
    if 'abteilung' in low or re.search(r'\babt\.', low) or re.search(r'\babt\b', low):
        return 'Abteilung'
    return 'Unknown'

# ─── Datums-Parsing ────────────────────────────────────────────────────────────

_MONAT = {
    'jan': 1, 'febr': 2, 'feb': 2, 'mär': 3, 'mar': 3,
    'apr': 4, 'mai': 5, 'jun': 6, 'jul': 7, 'aug': 8,
    'sept': 9, 'sep': 9, 'okt': 10, 'nov': 11, 'dez': 12,
}

def _first_month(s: str) -> int | None:
    s = s.lower()
    for prefix in sorted(_MONAT, key=len, reverse=True):
        if s.startswith(prefix):
            return _MONAT[prefix]
    return None

def parse_monat_range(jahr: int, monat_str: str) -> tuple[str, str, str]:
    """Gibt (begin_iso, end_iso, precision) zurück."""
    if not monat_str:
        return str(jahr), str(jahr), "year"

    s = re.sub(r'[^a-zäöüß./\-]', '', monat_str.lower().strip())
    # Trenne am Bereichstrenner
    parts = re.split(r'[./\-]+', s, maxsplit=1)
    m1 = _first_month(parts[0]) if parts else None
    m2 = _first_month(parts[1]) if len(parts) > 1 else None

    if m1 is None:
        return str(jahr), str(jahr), "year"

    begin = f"{jahr}-{m1:02d}"
    if m2 is None:
        end = f"{jahr}-{m1:02d}"
    elif m2 >= m1:
        end = f"{jahr}-{m2:02d}"
    else:
        end = f"{jahr + 1}-{m2:02d}"   # Jahreswechsel, z.B. Okt./Jan.

    return begin, end, "month"

# ─── Geocoding ─────────────────────────────────────────────────────────────────
# Format: name_lower → (lat, lon, precision, radius_km) oder None (schauplatz)

_GEO: dict[str, tuple | None] = {
    # Deutschland / West
    'heimat':         (51.0,  10.0, 'region', 150),
    'ostpreußen':     (54.2,  21.5, 'region', 120),
    'westpreußen':    (53.5,  18.5, 'region', 100),
    'pommern':        (53.8,  16.0, 'region', 120),
    'schlesien':      (51.0,  17.0, 'region', 120),
    'eifel':          (50.2,   6.5, 'region',  80),
    'eifel,':         (50.2,   6.5, 'region',  80),
    'saarpfalz':      (49.5,   6.8, 'region',  80),
    'lothringen':     (48.7,   6.2, 'region',  80),
    'niederrhein':    (51.4,   6.5, 'region',  80),
    'kanalküste':     (50.8,   1.8, 'region',  80),
    'bretagne':       (48.2,  -2.5, 'region',  80),
    'normandie':      (49.0,  -1.0, 'region',  80),
    'nordfrankreich': (50.0,   3.0, 'region', 100),
    'ostfrankreich':  (48.5,   6.5, 'region', 100),
    'frankreich':     (46.5,   2.5, 'region', 150),
    'belgien':        (50.5,   4.5, 'region', 100),
    'niederlande':    (52.3,   5.3, 'region',  80),
    'ardennen':       (50.0,   5.5, 'region',  70),
    'dänemark':       (56.0,  10.0, 'region', 120),
    # Ostfront Nord
    'leningrad':      (59.95, 30.32, 'stadt', 20),
    'nordrußland':    (59.0,  30.0, 'region', 150),
    'wolchow':        (59.5,  32.2, 'region', 100),
    'tichwin':        (59.65, 33.52, 'stadt',  25),
    'kurland':        (56.8,  23.0, 'region', 100),
    'newel':          (56.0,  29.7, 'stadt',   20),
    # Ostfront Mitte
    'minsk':          (53.9,  27.56, 'stadt',  20),
    'bialystok':      (53.13, 23.16, 'stadt',  20),
    'smolensk':       (54.78, 32.04, 'stadt',  20),
    'gshatsk':        (55.58, 34.99, 'stadt',  20),
    'welish':         (55.6,  31.2,  'stadt',  20),
    'orel':           (52.97, 36.06, 'stadt',  20),
    'brjansk':        (53.24, 34.36, 'stadt',  20),
    'kursk':          (51.73, 36.19, 'stadt',  20),
    'moskau':         (55.75, 37.62, 'region', 150),
    'witebsk':        (55.19, 30.21, 'stadt',  20),
    'polozk':         (55.49, 28.79, 'stadt',  20),
    # Ostfront Süd / Ukraine
    'kiew':           (50.45, 30.52, 'stadt',  20),
    'charkow':        (49.98, 36.25, 'stadt',  20),
    'stalingrad':     (48.71, 44.51, 'stadt',  20),
    'don':            (49.0,  40.0, 'region', 150),
    'donez':          (48.5,  37.5, 'region',  80),
    'mius':           (47.5,  38.5, 'region',  80),
    'taganrog':       (47.21, 38.91, 'stadt',  20),
    'rostow':         (47.23, 39.72, 'stadt',  20),
    'krim':           (45.0,  34.0, 'region',  80),
    'dnjepr':         (48.5,  35.0, 'region', 100),
    'shitomir':       (50.25, 28.67, 'stadt',  20),
    'winniza':        (49.23, 28.47, 'stadt',  20),
    'kamenez-podolsk':(48.68, 26.57, 'stadt',  20),
    'kam.-podolsk':   (48.68, 26.57, 'stadt',  20),
    'kam.podolsk':    (48.68, 26.57, 'stadt',  20),
    'lemberg':        (49.84, 24.03, 'stadt',  20),
    'brody':          (50.08, 25.15, 'stadt',  20),
    'tarnopol':       (49.55, 25.59, 'stadt',  20),
    'bessarabien':    (47.5,  28.5, 'region', 100),
    # Ostfront Polen / Weichsel
    'warschau':       (52.23, 21.01, 'stadt',  20),
    'baranow':        (50.48, 21.5,  'region',  50),
    'weichsel':       (50.5,  22.0,  'region', 100),
    'baranow,weichsel':(50.48, 21.5, 'region',  50),
    'weichselbogen':  (50.87, 20.63, 'region',  50),
    'kielce':         (50.87, 20.63, 'stadt',   20),
    'krakau':         (50.06, 19.94, 'stadt',   20),
    'radom':          (51.4,  21.15, 'stadt',   15),
    'oder':           (52.0,  14.5,  'region', 100),
    'schlesien,oder': (51.5,  15.5,  'region', 100),
    # Sonstige
    'stalingrad':     (48.71, 44.51, 'stadt',  20),
    'sizilien':       (37.5,  14.0,  'region', 100),
    'nordafrika':     (31.0,  13.0,  'region', 150),
    'libyen':         (28.0,  15.0,  'region', 150),
    'kroatien':       (45.1,  15.5,  'region', 100),
    'rumänien':       (45.8,  24.9,  'region', 150),
    'ungarn':         (47.0,  19.0,  'region', 120),
    'griechenland':   (39.5,  22.0,  'region', 150),
    'jugoslawien':    (44.0,  17.0,  'region', 150),
    'norweeen':       (62.0,  10.0,  'region', 150),
    'norwegen':       (62.0,  10.0,  'region', 150),
    'finnland':       (64.0,  26.0,  'region', 150),
    'italien':        (43.0,  12.0,  'region', 150),
    'süditalien':     (39.5,  16.0,  'region', 100),
    'Lothringen':     (48.7,   6.2,  'region',  80),
}

_THEATER_NOISE = {
    'osten','westen','heimat','nord','süd','mitte','süden','norden',
    'nordukr','nordukraine','-','','.',',','snd','ge','de','ee','pia',
    'nb','gci','nb','la','ob','se','lz','vu','cs','cs.','gce','gc'
}

def geocode(ort: str, detail: str = '', theater: str = '') -> dict | None:
    """Erstellt ein place-dict oder None."""
    candidates: list[str] = []

    raw = ort.strip().rstrip('.,')
    if raw and raw.lower() not in _THEATER_NOISE:
        candidates.append(raw)

    # Letztes Token aus detail
    if detail:
        toks = detail.split()
        if toks:
            t = toks[-1].rstrip('.,')
            if t.lower() not in _THEATER_NOISE and len(t) > 2 and t not in candidates:
                candidates.append(t)
        # Zweitletztes + letztes (Kombi-Ortname)
        if len(toks) >= 2:
            combo = (toks[-2] + toks[-1]).rstrip(',.')
            combo2 = (toks[-2] + ',' + toks[-1]).rstrip(',.')
            for c in (combo, combo2):
                if c.lower() not in _THEATER_NOISE and c not in candidates:
                    candidates.append(c)

    for cand in candidates:
        key = cand.lower().strip().rstrip(',.')
        if key in _GEO:
            entry = _GEO[key]
            if entry is None:
                return {"name": cand, "precision": "schauplatz",
                        "lat": None, "lon": None}
            lat, lon, prec, rad = entry
            place = {
                "name": cand,
                "lat": lat, "lon": lon,
                "precision": prec, "radius_km": rad,
                "place_source": f"Tessin Bd. {BAND}",
            }
            return place

    # Fallback: nur Name, schauplatz
    if candidates:
        name = candidates[0]
        if name.lower() not in _THEATER_NOISE and len(name) > 2:
            return {"name": name, "precision": "schauplatz",
                    "lat": None, "lon": None}
    return None

# ─── Einheitenname aufbereiten ──────────────────────────────────────────────────

def make_pref_label(nummer: str, einheit: str) -> str:
    n = nummer.strip()
    if n:
        return f"{n}. {einheit.strip()}"
    return einheit.strip()

def make_actor(actor_id: str, nummer: str, einheit: str,
               wehrkreis: str, heimatgarnison: str) -> dict:
    """Gibt vollständiges Actor-Dict zurück. Bei bekannter ID: aus DB nachladen."""
    # Bekannte ID: existierenden Actor ergänzen
    if actor_id in KNOWN_ACTOR_IDS.values():
        with db._get_conn() as conn:
            row = conn.execute(
                "SELECT data FROM actors WHERE id = ?", (actor_id,)
            ).fetchone()
        if row:
            existing = json.loads(row["data"])
            existing["tessin_band"] = BAND
            # Alt-Label aus Tessin hinzufügen
            tessin_name = make_pref_label(nummer, einheit)
            if tessin_name not in existing["alt_labels"] and tessin_name != existing["pref_label"]:
                existing["alt_labels"] = existing["alt_labels"] + [tessin_name]
            return existing

    # Neuer Actor
    hg = clean_heimatgarnison(heimatgarnison)
    wk = wehrkreis.strip() or None
    label = make_pref_label(nummer, einheit)

    actor: dict = {
        "id":         actor_id,
        "type":       "MilitaryUnit",
        "pref_label": label,
        "alt_labels": [],
        "abbr":       None,
        "branch":     derive_branch(einheit),
        "unit_type":  derive_unit_type(einheit),
        "heimatgarnison": hg,
        "wehrkreis":  wk,
        "parent_unit_id": None,
        "tessin_band": BAND,
        "tessin_seite": None,
        "family_name": None,
        "given_name":  None,
        "birth_date":  None,
        "death_date":  None,
        "birth_place": None,
        "notes":       None,
        "created_at":  CREATED,
    }
    return actor

# ─── Hauptkonvertierung ─────────────────────────────────────────────────────────

def run() -> None:
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    with_ust = [d for d in data if d.get("unterstellungen")]
    print(f"Einträge mit Unterstellungen: {len(with_ust)}")

    actors_inserted      = 0
    events_inserted      = 0
    participations_inserted = 0
    skipped_invalid      = 0
    event_id_counter: dict[str, int] = defaultdict(int)

    for entry in with_ust:
        nummer  = entry.get("nummer", "").strip()
        einheit = entry.get("einheit", "").strip()
        actor_id = make_actor_id(nummer, einheit)

        # Actor
        actor = make_actor(
            actor_id, nummer, einheit,
            entry.get("wehrkreis", ""),
            entry.get("heimatgarnison", ""),
        )
        try:
            db.insert_actor(actor)
            actors_inserted += 1
        except Exception as exc:
            print(f"  ACTOR FEHLER {actor_id}: {exc}")
            skipped_invalid += 1
            continue

        # UnitJoining-Events
        for u in entry["unterstellungen"]:
            jahr  = u.get("jahr")
            monat = u.get("monat", "")
            if not jahr:
                continue

            begin, end, prec_t = parse_monat_range(int(jahr), monat)

            # Eindeutige Event-ID
            m1, _ = parse_monat_range(int(jahr), monat)[:1], None
            _, m_num = divmod(int(begin.split("-")[1]) if "-" in begin else 1, 100)
            m_num = int(begin.split("-")[1]) if "-" in begin else 1
            base_id = make_event_id(actor_id, int(jahr), m_num)
            counter = event_id_counter[base_id]
            event_id_counter[base_id] += 1
            eid = base_id if counter == 0 else f"{base_id}_{counter}"

            # Quelle
            source = {
                "type":         "tessin",
                "certainty":    3,
                "generated_by": "direkt",
                "reference":    f"Tessin Bd. {BAND}",
                "page":         None,
            }

            # Ort
            place_raw = geocode(
                u.get("ort", ""),
                u.get("detail", ""),
                u.get("theater", ""),
            )

            # place auf Schema-Konformität bringen
            place: dict | None = None
            if place_raw:
                p = place_raw
                if p["precision"] == "schauplatz":
                    place = {
                        "name":      p["name"],
                        "precision": "schauplatz",
                        "lat":       None,
                        "lon":       None,
                    }
                else:
                    place = {
                        "name":       p["name"],
                        "lat":        p["lat"],
                        "lon":        p["lon"],
                        "precision":  p["precision"],
                        "radius_km":  p["radius_km"],
                        "place_source": p.get("place_source"),
                    }

            # unit_details
            unit_details = {
                "korps":        u.get("korps") or None,
                "armee":        u.get("armee") or None,
                "heeresgruppe": u.get("hgr")   or None,
                "theater":      u.get("theater") or None,
            }

            label = (
                f"{actor['pref_label']} Unterstellung "
                f"{begin[:7] if len(begin) >= 7 else begin}"
            )
            if u.get("armee"):
                label += f", {u['armee'].strip()}"
            if u.get("hgr"):
                label += f", Hgr. {u['hgr'].strip()}"

            event: dict = {
                "id":          eid,
                "type":        "UnitJoining",
                "label":       label,
                "time_span":   {
                    "begin":     begin,
                    "end":       end,
                    "precision": prec_t,
                },
                "source":      source,
                "unit_details": unit_details,
                "notes":       u.get("detail_raw") or None,
                "created_at":  CREATED,
            }
            if place:
                event["place"] = place

            try:
                db.insert_event(event)
                events_inserted += 1
            except Exception as exc:
                print(f"  EVENT FEHLER {eid}: {exc}")
                skipped_invalid += 1
                continue

            # Participation
            participation = {
                "event_id":   eid,
                "actor_id":   actor_id,
                "relation":   "had_participant",
                "role":       "unit",
                "created_at": CREATED,
            }
            try:
                db.insert_participation(participation)
                participations_inserted += 1
            except Exception as exc:
                print(f"  PARTICIPATION FEHLER {eid}: {exc}")
                skipped_invalid += 1

    # ─── Statistik ──────────────────────────────────────────────────────────────
    print()
    print("═" * 50)
    print(f"Eingefügt: {actors_inserted} Actors | {events_inserted} Events | {participations_inserted} Participations")
    if skipped_invalid:
        print(f"Übersprungen (Fehler): {skipped_invalid}")

    with db._get_conn() as conn:
        a = conn.execute("SELECT COUNT(*) FROM actors").fetchone()[0]
        e = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        p = conn.execute("SELECT COUNT(*) FROM participations").fetchone()[0]
    print(f"DB-Gesamt: {a} Actors | {e} Events | {p} Participations")
    print()

    # ─── Test: verorte unit_20_pz_gren_div August 1943 ─────────────────────────
    print("═" * 50)
    print("TEST: verorte('unit_20_pz_gren_div', '1943-08')")
    print("Erwartung: Orel-Raum, certainty=3, source_type=tessin")
    print("─" * 50)
    results = db.verorte("unit_20_pz_gren_div", "1943-08")
    if not results:
        print("  ✗  KEINE ERGEBNISSE")
    else:
        for r in results:
            place = r.get("place") or {}
            src   = r.get("source") or {}
            ud    = r.get("unit_details") or {}
            print(f"  event     : {r['id']}")
            print(f"  time_span : {r['time_span']['begin']} – {r['time_span']['end']}")
            print(f"  ort       : {place.get('name', '(schauplatz)')}  lat={place.get('lat')}  lon={place.get('lon')}")
            print(f"  certainty : {src.get('certainty')}  source={src.get('type')}")
            print(f"  korps     : {ud.get('korps')}  armee={ud.get('armee')}  hgr={ud.get('heeresgruppe')}  theater={ud.get('theater')}")
            print(f"  detail    : {r.get('notes')}")
            print()
        # Prüfung
        found_orel = any(
            'orel' in (r.get('place') or {}).get('name','').lower()
            or 'orel' in (r.get('notes') or '').lower()
            for r in results
        )
        if found_orel:
            print("  ✓  Orel-Raum gefunden")
        else:
            print("  ✗  Orel-Raum NICHT in Ergebnissen")

if __name__ == "__main__":
    run()
