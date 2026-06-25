#!/usr/bin/env python3
"""
load_all_tessin.py
Lädt alle Tessin-Bände in familiengeschichte.db.
- Actors (MilitaryUnit) + UnitJoining-Events + Participations
- UnitNaming-Events aus Textfeldern
- Deduplication: Actor nicht überschreiben wenn bereits vorhanden
"""

import argparse
import json
import re
import sys
import glob
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))
import db

CREATED = "2026-06-11"

# Garbage-Labels die niemals als Actor in die DB kommen sollen
_GARBAGE_LABELS = {
    'unterstellung', 'i', 'ii', 'iii', 'iv', 'v',
    'z.vfg.', '—', '-', 'x', 'xi', 'xii', 'xiii',
}


def is_valid_actor(pref_label: str) -> bool:
    s = pref_label.strip()
    if len(s) < 4:
        return False
    if s.lower() in _GARBAGE_LABELS:
        return False
    return True


# Mappt (nummer_strip, einheit_strip) → bekannte Actor-IDs aus actors.json
KNOWN_ACTOR_IDS: dict[tuple, str] = {
    ('20', 'Infanterie-Division (mot.)'): 'unit_20_pz_gren_div',
    ('20', 'Infanterie-Division (motorisiert)'): 'unit_20_inf_div_mot',
    ('20', 'Panzergrenadier-Division'): 'unit_20_pz_gren_div',
    ('20', 'Panzer-Division'): 'unit_20_pz_div',
    ('20', 'Nachrichten-Abteilung'): 'unit_na20',   # Langform (aus Normalisierung)
    ('20', 'Nachrichten-Abt.'): 'unit_na20',         # Tessin-Kurzform (nach trailing-Num-Strip)
    ('90', 'Grenadier-Regiment'): 'unit_pzgrenrgt90',
    ('90', 'Panzergrenadier-Regiment'): 'unit_pzgrenrgt90',
    ('90', 'Infanterie-Regiment'): 'unit_pzgrenrgt90',
}

# ─── ID-Normalisierung ──────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    s = s.lower()
    for a, b in [('ä', 'ae'), ('ö', 'oe'), ('ü', 'ue'), ('ß', 'ss')]:
        s = s.replace(a, b)
    s = re.sub(r'[^a-z0-9]+', '_', s)
    return re.sub(r'_+', '_', s).strip('_')


def make_actor_id(nummer: str, einheit: str) -> str:
    n = nummer.strip()
    e = einheit.strip()
    # Wenn einheit bereits die führende Nummer enthält (Fix 2), für Lookup und ID-Generierung strippen
    if n and (e.startswith(f'{n}.') or e.startswith(f'{n} ')):
        e = re.sub(r'^\d+\.?\s*', '', e).strip()
    key = (n, e)
    if key in KNOWN_ACTOR_IDS:
        return KNOWN_ACTOR_IDS[key]
    return f"unit_{_norm(n)}_{_norm(e)}" if n else f"unit_{_norm(e)}"


def make_unitjoining_id(actor_id: str, jahr: int, m_begin: int, counter: int = 0) -> str:
    suffix = f"{actor_id.removeprefix('unit_')}_{jahr}_{m_begin:02d}"
    base = f"event_unitjoining_{suffix}"
    return base if counter == 0 else f"{base}_{counter}"


def make_unitnaming_id(actor_id: str, date_slug: str, counter: int = 0) -> str:
    base = f"event_unitnaming_{actor_id.removeprefix('unit_')}_{date_slug}"
    return base if counter == 0 else f"{base}_{counter}"


# ─── Actor-Felder ───────────────────────────────────────────────────────────────

def clean_heimatgarnison(raw: str) -> str | None:
    s = re.sub(r'^\d+\s*', '', raw.strip()).strip()
    return s or None


def derive_branch(einheit: str) -> str:
    low = einheit.lower()
    if re.search(r'\bss[-\s.]', low) or 'waffen-ss' in low or 'waffen-gren' in low:
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
        end = f"{jahr + 1}-{m2:02d}"
    return begin, end, "month"


def parse_text_date(raw: str) -> tuple[str, str, str] | None:
    """Parst Datumsstring aus Textfeld → (begin, end, precision) oder None."""
    raw = raw.strip().replace(' ', '')
    # TT.MM.YYYY
    m = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$', raw)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31 and 1900 <= y <= 1950:
            iso = f"{y}-{mo:02d}-{d:02d}"
            return iso, iso, "day"
    # TT.MM.YY
    m = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{2})$', raw)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y += 1900
        if 1 <= mo <= 12 and 1 <= d <= 31 and 1900 <= y <= 1950:
            iso = f"{y}-{mo:02d}-{d:02d}"
            return iso, iso, "day"
    # MM.YYYY or M.YYYY
    m = re.match(r'^(\d{1,2})\.(\d{4})$', raw)
    if m:
        mo, y = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1900 <= y <= 1950:
            iso = f"{y}-{mo:02d}"
            return iso, iso, "month"
    # YYYY alone
    m = re.match(r'^(\d{4})$', raw)
    if m:
        y = int(m.group(1))
        if 1900 <= y <= 1950:
            return str(y), str(y), "year"
    return None


def date_to_slug(begin: str) -> str:
    return begin.replace('-', '_')


# ─── Geocoding ─────────────────────────────────────────────────────────────────

_GEO: dict[str, tuple | None] = {
    # Deutschland / West
    'heimat':         (51.0,  10.0, 'region', 150),
    'deutschland':    (51.0,  10.0, 'region', 150),
    'ostpreußen':     (54.2,  21.5, 'region', 120),
    'westpreußen':    (53.5,  18.5, 'region', 100),
    'pommern':        (53.8,  16.0, 'region', 120),
    'schlesien':      (51.0,  17.0, 'region', 120),
    'eifel':          (50.2,   6.5, 'region',  80),
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
    'holland':        (52.3,   5.3, 'region',  80),
    'ardennen':       (50.0,   5.5, 'region',  70),
    'dänemark':       (56.0,  10.0, 'region', 120),
    # Ostfront Nord
    'leningrad':      (59.95, 30.32, 'stadt',  20),
    'nordrußland':    (59.0,  30.0, 'region', 150),
    'wolchow':        (59.5,  32.2, 'region', 100),
    'tichwin':        (59.65, 33.52, 'stadt',  25),
    'kurland':        (56.8,  23.0, 'region', 100),
    'newel':          (56.0,  29.7, 'stadt',   20),
    'narwa':          (59.38, 28.19, 'stadt',  20),
    'narva':          (59.38, 28.19, 'stadt',  20),
    'riga':           (56.95, 24.11, 'stadt',  20),
    'estland':        (58.5,  25.0, 'region', 100),
    'lettland':       (56.9,  24.6, 'region', 100),
    'litauen':        (55.4,  24.0, 'region', 100),
    'pskov':          (57.82, 28.33, 'stadt',  20),
    'pleskau':        (57.82, 28.33, 'stadt',  20),
    # Ostfront Mitte
    'minsk':          (53.9,  27.56, 'stadt',  20),
    'bialystok':      (53.13, 23.16, 'stadt',  20),
    'białystok':      (53.13, 23.16, 'stadt',  20),
    'smolensk':       (54.78, 32.04, 'stadt',  20),
    'gshatsk':        (55.58, 34.99, 'stadt',  20),
    'gzhatsk':        (55.58, 34.99, 'stadt',  20),
    'welish':         (55.6,  31.2,  'stadt',  20),
    'orel':           (52.97, 36.06, 'stadt',  20),
    'brjansk':        (53.24, 34.36, 'stadt',  20),
    'bryansk':        (53.24, 34.36, 'stadt',  20),
    'kursk':          (51.73, 36.19, 'stadt',  20),
    'moskau':         (55.75, 37.62, 'region', 150),
    'witebsk':        (55.19, 30.21, 'stadt',  20),
    'polozk':         (55.49, 28.79, 'stadt',  20),
    'bobruisk':       (53.15, 29.22, 'stadt',  20),
    'mogilew':        (53.9,  30.33, 'stadt',  20),
    'gomel':          (52.44, 31.0,  'stadt',  20),
    'wjasma':         (55.21, 34.29, 'stadt',  20),
    'rshew':          (56.26, 34.32, 'stadt',  20),
    'rzhev':          (56.26, 34.32, 'stadt',  20),
    'demjansk':       (57.64, 32.47, 'region',  50),
    'ilmen':          (58.27, 31.25, 'region',  50),
    # Ostfront Süd / Ukraine
    'kiew':           (50.45, 30.52, 'stadt',  20),
    'charkow':        (49.98, 36.25, 'stadt',  20),
    'kharkov':        (49.98, 36.25, 'stadt',  20),
    'stalingrad':     (48.71, 44.51, 'stadt',  20),
    'don':            (49.0,  40.0, 'region', 150),
    'donez':          (48.5,  37.5, 'region',  80),
    'donbass':        (48.0,  38.0, 'region',  80),
    'mius':           (47.5,  38.5, 'region',  80),
    'taganrog':       (47.21, 38.91, 'stadt',  20),
    'rostow':         (47.23, 39.72, 'stadt',  20),
    'krim':           (45.0,  34.0, 'region',  80),
    'sewastopol':     (44.62, 33.52, 'stadt',  20),
    'kertsch':        (45.36, 36.47, 'stadt',  20),
    'dnjepr':         (48.5,  35.0, 'region', 100),
    'dnepropetrowsk': (48.46, 35.04, 'stadt',  20),
    'saporoshje':     (47.84, 35.14, 'stadt',  20),
    'nikopol':        (47.57, 34.4,  'stadt',  20),
    'shitomir':       (50.25, 28.67, 'stadt',  20),
    'schytomyr':      (50.25, 28.67, 'stadt',  20),
    'winniza':        (49.23, 28.47, 'stadt',  20),
    'kamenez-podolsk': (48.68, 26.57, 'stadt', 20),
    'kam.-podolsk':   (48.68, 26.57, 'stadt',  20),
    'lemberg':        (49.84, 24.03, 'stadt',  20),
    'lwow':           (49.84, 24.03, 'stadt',  20),
    'brody':          (50.08, 25.15, 'stadt',  20),
    'tarnopol':       (49.55, 25.59, 'stadt',  20),
    'odessa':         (46.48, 30.73, 'stadt',  20),
    'nikolajew':      (46.97, 32.0,  'stadt',  20),
    'cherson':        (46.65, 32.62, 'stadt',  20),
    'bessarabien':    (47.5,  28.5, 'region', 100),
    # Ostfront Polen / Weichsel
    'warschau':       (52.23, 21.01, 'stadt',  20),
    'baranow':        (50.48, 21.5,  'region',  50),
    'weichsel':       (50.5,  22.0,  'region', 100),
    'baranow,weichsel': (50.48, 21.5, 'region', 50),
    'weichselbogen':  (50.87, 20.63, 'region',  50),
    'kielce':         (50.87, 20.63, 'stadt',   20),
    'krakau':         (50.06, 19.94, 'stadt',   20),
    'radom':          (51.4,  21.15, 'stadt',   15),
    'lublin':         (51.25, 22.57, 'stadt',   20),
    'brest':          (52.1,  23.7,  'stadt',   20),
    'oder':           (52.0,  14.5,  'region', 100),
    'stettin':        (53.43, 14.55, 'stadt',   20),
    # Balkan / Südost
    'sizilien':       (37.5,  14.0,  'region', 100),
    'nordafrika':     (31.0,  13.0,  'region', 150),
    'libyen':         (28.0,  15.0,  'region', 150),
    'tunesien':       (34.0,   9.0,  'region', 150),
    'kroatien':       (45.1,  15.5,  'region', 100),
    'serbien':        (44.0,  21.0,  'region', 100),
    'bosnien':        (44.0,  17.5,  'region', 100),
    'rumänien':       (45.8,  24.9,  'region', 150),
    'ungarn':         (47.0,  19.0,  'region', 120),
    'budapest':       (47.5,  19.0,  'stadt',   20),
    'griechenland':   (39.5,  22.0,  'region', 150),
    'jugoslawien':    (44.0,  17.0,  'region', 150),
    'bulgarien':      (42.7,  25.5,  'region', 150),
    # Nord
    'norwegen':       (62.0,  10.0,  'region', 150),
    'norweeen':       (62.0,  10.0,  'region', 150),
    'finnland':       (64.0,  26.0,  'region', 150),
    # Sonstige
    'italien':        (43.0,  12.0,  'region', 150),
    'süditalien':     (39.5,  16.0,  'region', 100),
    'norditalien':    (44.5,  11.0,  'region', 100),
    'sudrussland':    (48.0,  36.0,  'region', 150),
    'südrußland':     (48.0,  36.0,  'region', 150),
    'südrussland':    (48.0,  36.0,  'region', 150),
    'kaukasus':       (43.0,  43.0,  'region', 150),
    'iran':           (32.0,  53.0,  'region', 200),
}

_THEATER_NOISE = {
    'osten', 'westen', 'heimat', 'nord', 'süd', 'mitte', 'süden', 'norden',
    'nordukr', 'nordukraine', '-', '', '.', ',', 'snd', 'ge', 'de', 'ee', 'pia',
    'nb', 'gci', 'la', 'ob', 'se', 'lz', 'vu', 'cs', 'gce', 'gc', 'nb',
}


def geocode(ort: str | None, detail: str = '', theater: str = '', band: int = 0) -> dict | None:
    candidates: list[str] = []
    raw = (ort or '').strip().rstrip('.,')
    if raw and raw.lower() not in _THEATER_NOISE:
        candidates.append(raw)
    if detail:
        toks = detail.split()
        if toks:
            t = toks[-1].rstrip('.,')
            if t.lower() not in _THEATER_NOISE and len(t) > 2 and t not in candidates:
                candidates.append(t)
        if len(toks) >= 2:
            combo = toks[-2].rstrip('.,') + toks[-1].rstrip('.,')
            combo2 = toks[-2].rstrip('.,') + ',' + toks[-1].rstrip('.,')
            for c in (combo, combo2):
                if c.lower() not in _THEATER_NOISE and c not in candidates:
                    candidates.append(c)

    for cand in candidates:
        key = cand.lower().strip().rstrip(',.')
        if key in _GEO:
            entry = _GEO[key]
            if entry is None:
                return {"name": cand, "precision": "schauplatz", "lat": None, "lon": None}
            lat, lon, prec, rad = entry
            return {
                "name": cand, "lat": lat, "lon": lon,
                "precision": prec, "radius_km": rad,
                "place_source": f"Tessin Bd. {band}" if band else "Tessin",
            }

    if candidates:
        name = candidates[0]
        if name.lower() not in _THEATER_NOISE and len(name) > 2:
            return {"name": name, "precision": "schauplatz", "lat": None, "lon": None}
    return None


def place_for_schema(p: dict | None) -> dict | None:
    if p is None:
        return None
    if p["precision"] == "schauplatz":
        return {"name": p["name"], "precision": "schauplatz", "lat": None, "lon": None}
    return {
        "name": p["name"],
        "lat": p["lat"], "lon": p["lon"],
        "precision": p["precision"], "radius_km": p["radius_km"],
        "place_source": p.get("place_source"),
    }


# ─── Actor-Builder ─────────────────────────────────────────────────────────────

_UNIT_EXPANSIONS: dict[str, str] = {}

def _get_unit_expansions() -> dict[str, str]:
    global _UNIT_EXPANSIONS
    if not _UNIT_EXPANSIONS:
        p = Path(__file__).parent / "wast_abbreviations.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        _UNIT_EXPANSIONS = data["kategorien"]["einheiten"]
    return _UNIT_EXPANSIONS


def _expand_unit_name(s: str) -> str:
    """Ersetzt Abkürzungen: 'Nachrichten-Abt.' → 'Nachrichten-Abteilung'."""
    exp = _get_unit_expansions()
    for key in sorted(exp, key=len, reverse=True):
        s = s.replace(key, exp[key])
    return s


UMBENENNUNG_RE = re.compile(r'\n([A-ZÄÖÜ][^\n]+?\d+)\s*seit\s*\d')


def extract_umbenennungen(raw_text: str) -> list[str]:
    """Extrahiert spätere Bezeichnungen aus Tessin-Fließtext.

    Muster: 'NeuerName seit Datum' — Name steht nach Zeilenumbruch,
    Datum direkt nach 'seit' (kein Leerzeichen nötig).
    Komposita wie 'Ers.bzw.Ausb.' werden auf den ersten Typ reduziert.
    """
    names = []
    for name in UMBENENNUNG_RE.findall(raw_text):
        name = re.sub(r'\s*bzw\.\s*\w+\.', '', name)
        name = re.sub(r'\s*und\s*\w+\.', '', name)
        name = re.sub(r'\s{2,}', ' ', name).strip()
        expanded = _expand_unit_name(name)
        expanded = re.sub(r'([a-zäöüß)])(\d)', r'\1 \2', expanded)
        if len(expanded) >= 4:
            names.append(expanded)
    return names


def make_alt_labels(nummer: str, einheit: str, raw_text: str = '') -> list[str]:
    """Erzeugt alle Schreibvarianten für entity_linking."""
    # Führende Nummer aus einheit strippen (Pattern A: "20.Infanterie-Division")
    prefix = re.match(r'^\d+\.\s*', einheit)
    body = einheit[prefix.end():] if prefix else einheit

    expanded = _expand_unit_name(body)
    expanded = re.sub(r'([a-zäöüß])(\d)', r'\1 \2', expanded)
    pref = make_pref_label(nummer, einheit)

    labels: set[str] = set()
    if nummer:
        labels.add(f"{body} {nummer}")        # "Nachrichten-Abt. 20"
        labels.add(f"{nummer}. {body}")       # "20. Nachrichten-Abt."
        labels.add(f"{expanded} {nummer}")    # "Nachrichten-Abteilung 20"  ← primärer Query-Treffer
        labels.add(f"{nummer}. {expanded}")   # "20. Nachrichten-Abteilung"
    else:
        labels.add(body)
        labels.add(expanded)

    for umb in extract_umbenennungen(raw_text):
        labels.add(umb)

    labels.discard(pref)            # pref_label nicht doppelt speichern
    labels.discard("")
    return sorted(l for l in labels if len(l) >= 4)


def make_pref_label(nummer: str, einheit: str) -> str:
    if not nummer:
        return einheit
    # Nummer-Prefix aus einheit strippen falls vorhanden (Fix 2: name_raw enthält führende Nummer)
    prefix = re.match(r'^\d+\.\s*', einheit)
    if prefix:
        einheit = einheit[prefix.end():]
    return f"{nummer}. {einheit}"


def actor_exists(actor_id: str) -> bool:
    with db._get_conn() as conn:
        row = conn.execute("SELECT 1 FROM actors WHERE id = ?", (actor_id,)).fetchone()
    return row is not None


def make_actor(actor_id: str, nummer: str, einheit: str,
               wehrkreis: str, heimatgarnison: str, band: int,
               raw_text: str = '') -> dict:
    if actor_id in KNOWN_ACTOR_IDS.values():
        with db._get_conn() as conn:
            row = conn.execute("SELECT data FROM actors WHERE id = ?", (actor_id,)).fetchone()
        if row:
            return json.loads(row["data"])

    hg = clean_heimatgarnison(heimatgarnison)
    wk = wehrkreis.strip() or None
    label = make_pref_label(nummer, einheit)
    return {
        "id": actor_id,
        "type": "MilitaryUnit",
        "pref_label": label,
        "alt_labels": make_alt_labels(nummer, einheit, raw_text),
        "abbr": None,
        "branch": derive_branch(einheit),
        "unit_type": derive_unit_type(einheit),
        "heimatgarnison": hg,
        "wehrkreis": wk,
        "parent_unit_id": None,
        "tessin_band": band,
        "tessin_seite": None,
        "family_name": None,
        "given_name": None,
        "birth_date": None,
        "death_date": None,
        "birth_place": None,
        "notes": None,
        "created_at": CREATED,
    }


# ─── Parent-Unit-Auflösung ────────────────────────────────────────────────────

def _first_parent_candidate(ueberstellung_kurz: str) -> str | None:
    """Extrahiert den ersten Einheitsnamen aus ueberstellung_kurz.

    U:-Inhalte haben oft die Form:
      "29.Inf.Div.(mot.): 1939 ...; 1940 ..."  → "29.Inf.Div.(mot.)"
      "Div. 159; 1.10.1942 189.Res.Div."        → "Div. 159"
      "189. Inf.Div. (B), Frankreich"            → "189. Inf.Div. (B)"
    Strategie: erstes Segment (vor ;) nehmen, dann Datums-Kontext abschneiden.
    """
    if not ueberstellung_kurz:
        return None
    # Erstes Segment vor Semikolon
    segment = ueberstellung_kurz.split(';')[0].strip()
    # Alles ab ": YYYY" oder ": 1" abschneiden (Einsatz-/Stationsangaben)
    segment = re.sub(r':\s*\d.*', '', segment).strip()
    # Trailing geo-Noise (Komma + Theater) entfernen
    segment = re.sub(r',\s*[A-ZÄÖÜ][a-zA-Züöäß\-]+\s*$', '', segment).strip()
    segment = segment.rstrip('.,')
    return segment if len(segment) >= 4 else None


def _extract_number(s: str) -> str | None:
    """Extrahiert führende Zahl aus einem Einheitsnamen, z.B. '20.Inf.Div.' → '20'."""
    m = re.match(r'(\d+)', s.strip())
    return m.group(1) if m else None


def _token_overlap(query: str, label: str) -> int:
    """Zählt nützliche Tokens aus query die als Präfix in label vorkommen.

    'Inf' matcht 'Infanterie', 'mot' matcht 'mot'. Typ-Worte ('Div', 'Division'
    etc.) und Zahlen werden ignoriert — sie wurden bereits als Filterkriterium
    genutzt.
    """
    _STOPS = {
        'div', 'division', 'abt', 'abteilung', 'btl', 'bataillon',
        'rgt', 'regiment', 'kp', 'kompanie', 'korps', 'armee',
    }
    norm_label = re.sub(r'[^\wäöüß]', '', label.lower())
    tokens = re.findall(r'[a-zäöüß]{3,}', query.lower())
    useful = [t for t in tokens if t not in _STOPS]
    return sum(1 for t in useful if t in norm_label)


def resolve_parent_id(parent_text: str | None) -> str | None:
    """Strukturierte parent-Auflösung: Nummer + Typ → DB-Lookup.

    Statt Fuzzy-Matching: extrahiere Nummer und Einheitentyp aus dem Text,
    suche in der DB nach Actors mit passender Nummer im pref_label und
    gleichem unit_type. Bei mehreren Treffern: höchster Token-Overlap mit
    dem Suchbegriff, dann kürzestes pref_label.
    """
    if not parent_text:
        return None
    candidate = _first_parent_candidate(parent_text)
    if not candidate:
        return None

    nummer = _extract_number(candidate)
    if not nummer:
        return None

    unit_type = derive_unit_type(candidate)
    if unit_type == 'Unknown':
        return None

    # Garbage-Muster in pref_labels (OCR-Artefakte, eingebettete U:-Felder)
    _GARBAGE = re.compile(r'U:|[|!>]|\d{4}')

    with db._get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, pref_label FROM actors
            WHERE type = 'MilitaryUnit'
              AND json_extract(data, '$.unit_type') = ?
              AND pref_label LIKE ?
            """,
            (unit_type, f"{nummer}. %"),
        ).fetchall()

    # Garbage-Filter + Längen-Obergrenze (echte Divisionsnamen < 70 Zeichen)
    rows = [
        (aid, lbl) for aid, lbl in rows
        if not _GARBAGE.search(lbl) and len(lbl) <= 70
    ]

    if not rows:
        return None
    if len(rows) == 1:
        return rows[0][0]

    # Sortiere: höchster Token-Overlap zuerst, dann kürzestes Label
    rows.sort(key=lambda r: (-_token_overlap(candidate, r[1]), len(r[1])))
    return rows[0][0]


def _from_roman(s: str) -> int | None:
    """Konvertiert römische Zahl zu int. Gibt None bei ungültigem Input."""
    vals = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    s = s.upper().rstrip('.')
    if not s or not all(c in vals for c in s):
        return None
    result, prev = 0, 0
    for c in reversed(s):
        v = vals[c]
        result = result - v if v < prev else result + v
        prev = v
    return result if result > 0 else None


def _resolve_superior_actor(unit_details: dict) -> str | None:
    """Versucht den übergeordneten Verband (Korps oder Armee) als Actor-ID aufzulösen."""
    for field, utype in [('korps', 'Korps'), ('armee', 'Armee')]:
        val = (unit_details.get(field) or '').strip()
        if not val or val.lower() in ('z.vfg.', '—', '-', ''):
            continue
        # Römische Zahl (z.B. "XXXIX", "XIV")
        m_roman = re.match(r'^([IVXivxLlCcDdMm]+)\.?', val)
        # Arabische Zahl (z.B. "4.Armee", "18. Armee")
        m_arabic = re.match(r'^(\d+)', val)
        if m_roman:
            num = _from_roman(m_roman.group(1))
            if num is None:
                continue
            num_str = str(num)
        elif m_arabic:
            num_str = m_arabic.group(1)
        else:
            continue
        parent_id = resolve_parent_id(f"{num_str}. {utype}")
        if parent_id:
            return parent_id
    return None


def set_parent_unit_id(actor_id: str, parent_id: str) -> bool:
    """Setzt parent_unit_id auf einem Actor, falls noch None. Gibt True bei Änderung."""
    with db._get_conn() as conn:
        row = conn.execute("SELECT data FROM actors WHERE id = ?", (actor_id,)).fetchone()
        if not row:
            return False
        d = json.loads(row["data"])
        if d.get("parent_unit_id"):
            return False  # bereits gesetzt, nicht überschreiben
        d["parent_unit_id"] = parent_id
        conn.execute("UPDATE actors SET data = ? WHERE id = ?",
                     (json.dumps(d, ensure_ascii=False), actor_id))
    return True


# ─── UnitNaming-Extraktion ─────────────────────────────────────────────────────

# Regex: finde "umbenannt in X" mit vorangehendem Datum
_NAMING_RE = re.compile(
    # Datum-Gruppe: TT.MM.YYYY | TT.MM.YY | M. YYYY | YYYY
    r'(\d{1,2}\.\s*\d{1,2}\.\s*\d{2,4}|\d{1,2}\.\s*\d{4}|\d{4})'
    r'[^;]{0,80}?'
    r'umbenannt\s+in\s+'
    r'([A-ZÄÖÜ0-9][^;,\n]{2,60})',
    re.IGNORECASE,
)

# Alternativ: "in X umbenannt" mit Datum davor
_NAMING_RE2 = re.compile(
    r'(\d{1,2}\.\s*\d{1,2}\.\s*\d{2,4}|\d{1,2}\.\s*\d{4}|\d{4})'
    r'[^;]{0,60}?'
    r'in\s+([A-ZÄÖÜ0-9][^;,\n]{3,60}?)\s+umbenannt',
    re.IGNORECASE,
)

_TEXT_FIELDS = ('aufgestellt', 'ueberstellung_kurz', 'gliederung', 'ersatz')


def extract_naming_events(entry: dict, actor_id: str, actor_label: str,
                           band: int, naming_id_counter: dict) -> list[tuple[dict, dict]]:
    """Gibt Liste von (event_dict, participation_dict) zurück."""
    results = []
    seen_slugs: set[str] = set()

    all_text = []
    for f in _TEXT_FIELDS:
        val = entry.get(f) or ''
        if val:
            all_text.append(val)
    combined = '; '.join(all_text)

    for pattern in (_NAMING_RE, _NAMING_RE2):
        for m in pattern.finditer(combined):
            date_raw = re.sub(r'\s+', '', m.group(1))
            new_name = m.group(2).strip().rstrip('.,;)')

            parsed = parse_text_date(date_raw)
            if parsed is None:
                continue
            begin, end, precision = parsed

            # Dedupliziere innerhalb dieses Eintrags
            slug = date_to_slug(begin) + '_' + _norm(new_name[:20])
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)

            date_slug = date_to_slug(begin)
            counter = naming_id_counter[f"{actor_id}_{date_slug}"]
            naming_id_counter[f"{actor_id}_{date_slug}"] += 1
            eid = make_unitnaming_id(actor_id, date_slug, counter)

            event: dict = {
                "id": eid,
                "type": "UnitNaming",
                "label": f"{actor_label} → {new_name[:60]}",
                "time_span": {
                    "begin": begin,
                    "end": end,
                    "precision": precision,
                },
                "source": {
                    "type": "tessin",
                    "certainty": 3,
                    "generated_by": "direkt",
                    "reference": f"Tessin Bd. {band}",
                    "page": None,
                },
                "notes": m.group(0)[:200],
                "created_at": CREATED,
            }
            participation: dict = {
                "event_id": eid,
                "actor_id": actor_id,
                "relation": "had_participant",
                "role": "unit",
                "created_at": CREATED,
            }
            results.append((event, participation))

    return results


# ─── Pro-Band-Loader ───────────────────────────────────────────────────────────

def load_band(path: Path, band: int) -> dict:
    """Lädt einen Tessin-Band. Gibt Statistik-Dict zurück."""
    data = json.load(path.open(encoding='utf-8'))

    stats = {
        'band': band,
        'actors_new': 0, 'actors_existing': 0,
        'unitjoining_new': 0, 'unitnaming_new': 0,
        'participations_new': 0,
        'errors': 0,
    }

    with_ust = [e for e in data if e.get('unterstellungen')]
    all_entries = data

    event_id_counter: dict[str, int] = defaultdict(int)
    naming_id_counter: dict[str, int] = defaultdict(int)

    # Schritt 0: Actors für alle Einträge anlegen (unabhängig von Unterstellungen)
    for entry in all_entries:
        nummer = entry.get('nummer', '').strip()
        einheit = entry.get('einheit', '').strip()
        if not einheit:
            continue
        label = make_pref_label(nummer, einheit)
        if not is_valid_actor(label):
            continue
        actor_id = make_actor_id(nummer, einheit)
        if actor_exists(actor_id):
            stats['actors_existing'] += 1
        else:
            actor = make_actor(actor_id, nummer, einheit,
                               entry.get('wehrkreis', ''),
                               entry.get('heimatgarnison', ''), band,
                               entry.get('_raw_text', ''))
            try:
                db.insert_actor(actor)
                stats['actors_new'] += 1
            except Exception as exc:
                print(f"  [Bd.{band}] ACTOR FEHLER {actor_id}: {exc}")
                stats['errors'] += 1

    # Schritt 1: UnitJoining aus Einträgen mit Unterstellungen
    for entry in with_ust:
        nummer = entry.get('nummer', '').strip()
        einheit = entry.get('einheit', '').strip()
        if not einheit:
            continue
        if not is_valid_actor(make_pref_label(nummer, einheit)):
            continue

        actor_id = make_actor_id(nummer, einheit)

        # UnitJoining-Events
        for u in entry['unterstellungen']:
            jahr = u.get('jahr')
            monat = u.get('monat', '')
            if not jahr:
                continue
            begin, end, prec_t = parse_monat_range(int(jahr), monat)
            m_num = int(begin.split('-')[1]) if '-' in begin else 1
            base_id = make_unitjoining_id(actor_id, int(jahr), m_num)
            counter = event_id_counter[base_id]
            event_id_counter[base_id] += 1
            eid = base_id if counter == 0 else f"{base_id}_{counter}"

            place = place_for_schema(geocode(
                u.get('ort', ''), u.get('detail', ''),
                u.get('theater', ''), band
            ))
            unit_details = {
                'korps': u.get('korps') or None,
                'armee': u.get('armee') or None,
                'heeresgruppe': u.get('hgr') or None,
                'theater': u.get('theater') or None,
            }
            label = f"{make_pref_label(nummer, einheit)} Unterstellung {begin[:7] if len(begin) >= 7 else begin}"
            if u.get('armee'):
                label += f", {u['armee'].strip()}"
            if u.get('hgr'):
                label += f", Hgr. {u['hgr'].strip()}"

            event: dict = {
                "id": eid,
                "type": "UnitJoining",
                "label": label,
                "time_span": {"begin": begin, "end": end, "precision": prec_t},
                "source": {
                    "type": "tessin", "certainty": 3,
                    "generated_by": "direkt",
                    "reference": f"Tessin Bd. {band}",
                    "page": None,
                },
                "unit_details": unit_details,
                "notes": u.get('detail_raw') or None,
                "created_at": CREATED,
            }
            if place:
                event["place"] = place

            try:
                db.insert_event(event)
                stats['unitjoining_new'] += 1
            except Exception as exc:
                print(f"  [Bd.{band}] EVENT FEHLER {eid}: {exc}")
                stats['errors'] += 1
                continue

            # Participation: untergeordnete Einheit (joined)
            try:
                db.insert_participation({
                    "event_id": eid, "actor_id": actor_id,
                    "relation": "had_participant", "role": "joined",
                    "created_at": CREATED,
                })
                stats['participations_new'] += 1
            except Exception as exc:
                print(f"  [Bd.{band}] PART FEHLER {eid}: {exc}")
                stats['errors'] += 1

            # Participation: übergeordneter Verband (joined_with) — optional, nur wenn auflösbar
            superior_id = _resolve_superior_actor(unit_details)
            if superior_id and superior_id != actor_id:
                try:
                    db.insert_participation({
                        "event_id": eid, "actor_id": superior_id,
                        "relation": "had_participant", "role": "joined_with",
                        "created_at": CREATED,
                    })
                    stats['participations_new'] += 1
                except Exception:
                    pass

    # Schritt 2: UnitNaming aus allen Einträgen (auch ohne Unterstellungen)
    for entry in all_entries:
        nummer = entry.get('nummer', '').strip()
        einheit = entry.get('einheit', '').strip()
        if not einheit:
            continue
        actor_id = make_actor_id(nummer, einheit)
        actor_label = make_pref_label(nummer, einheit)

        naming_pairs = extract_naming_events(entry, actor_id, actor_label,
                                              band, naming_id_counter)
        for event, participation in naming_pairs:
            # Actor ggf. anlegen (für Einträge ohne Unterstellungen)
            if not actor_exists(actor_id):
                actor = make_actor(actor_id, nummer, einheit,
                                   entry.get('wehrkreis', ''),
                                   entry.get('heimatgarnison', ''), band,
                                   entry.get('_raw_text', ''))
                try:
                    db.insert_actor(actor)
                    stats['actors_new'] += 1
                except Exception:
                    pass

            try:
                db.insert_event(event)
                stats['unitnaming_new'] += 1
            except Exception as exc:
                print(f"  [Bd.{band}] NAMING FEHLER {event['id']}: {exc}")
                stats['errors'] += 1
                continue

            try:
                db.insert_participation(participation)
                stats['participations_new'] += 1
            except Exception as exc:
                print(f"  [Bd.{band}] NAMING PART FEHLER: {exc}")
                stats['errors'] += 1

    # Schritt 3: parent_unit_id aus ueberstellung_parent (neu) bzw. ueberstellung_kurz (Fallback)
    stats['parent_set'] = 0
    for entry in all_entries:
        nummer = entry.get('nummer', '').strip()
        einheit = entry.get('einheit', '').strip()
        if not einheit:
            continue
        # Bevorzuge neues ueberstellung_parent_name-Feld; Fallback: ueberstellung_kurz
        parent_text = entry.get('ueberstellung_parent_name') or entry.get('ueberstellung_kurz')
        if not parent_text:
            continue
        actor_id = make_actor_id(nummer, einheit)
        if not actor_exists(actor_id):
            continue
        parent_id = resolve_parent_id(parent_text)
        if parent_id and parent_id != actor_id:
            if set_parent_unit_id(actor_id, parent_id):
                stats['parent_set'] += 1

    return stats


# ─── Hauptprogramm ─────────────────────────────────────────────────────────────

def band_key(path: Path) -> tuple:
    """Sortierschlüssel: Bd.16-1 → (16, 1), Bd.4 → (4, 0)"""
    name = path.stem  # "tessin_bd4_final" oder "tessin_bd16-1_final"
    m = re.search(r'bd(\d+)(?:-(\d+))?', name)
    if m:
        return (int(m.group(1)), int(m.group(2) or 0))
    return (999, 0)


def _band_str_from_path(path: Path) -> str:
    """Extrahiert Band-String aus Dateiname: 'tessin_bd16-1_final' → '16-1'."""
    m = re.search(r'bd(\d+(?:-\d+)?)', path.stem)
    return m.group(1) if m else ''


def run() -> None:
    parser = argparse.ArgumentParser(description='Tessin-Bände in DB laden')
    parser.add_argument('--band', action='append', metavar='N',
                        help='Nur diesen Band laden (wiederholbar, z.B. --band 4 --band 6)')
    args = parser.parse_args()

    all_finals = sorted(Path('.').glob('tessin_bd*_final.json'), key=band_key)

    if args.band:
        band_filter = set(args.band)
        files = [f for f in all_finals if _band_str_from_path(f) in band_filter]
        if not files:
            print(f"Keine Dateien für --band {', '.join(sorted(band_filter))} gefunden.")
            sys.exit(1)
    else:
        files = all_finals

    if not files:
        print("Keine tessin_bd*_final.json Dateien gefunden.")
        sys.exit(1)

    print(f"Gefunden: {len(files)} Tessin-Bände\n")

    # Bereits geladene Bände (Bd.4 über load_tessin_bd4.py)
    with db._get_conn() as conn:
        already = {
            row[0] for row in conn.execute(
                "SELECT DISTINCT json_extract(data,'$.tessin_band') FROM actors "
                "WHERE json_extract(data,'$.tessin_band') IS NOT NULL"
            ).fetchall()
        }
    # Bd.4 bereits geladen — aber wir laden es nochmal für UnitNaming
    # (INSERT OR REPLACE ist idempotent für Events/Participations)

    all_stats = []
    total_naming = 0

    print(f"{'Band':>6}  {'Act.neu':>8}  {'Act.vor':>8}  {'Join.':>7}  {'Nam.':>7}  {'Fehler':>6}")
    print('─' * 55)

    for f in files:
        m = re.search(r'bd(\d+(?:-\d+)?)', f.stem)
        band_str = m.group(1) if m else '?'
        band_int = int(band_str.split('-')[0])  # 16-1 → 16

        stats = load_band(f, band_int)
        all_stats.append(stats)
        total_naming += stats['unitnaming_new']

        print(f"  Bd.{band_str:>4}: "
              f"  act_new={stats['actors_new']:4d}"
              f"  act_ex={stats['actors_existing']:4d}"
              f"  join={stats['unitjoining_new']:5d}"
              f"  naming={stats['unitnaming_new']:4d}"
              f"  parent={stats.get('parent_set', 0):4d}"
              f"  err={stats['errors']:3d}")

    # Gesamtstatistik
    with db._get_conn() as conn:
        a = conn.execute("SELECT COUNT(*) FROM actors").fetchone()[0]
        e = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        p = conn.execute("SELECT COUNT(*) FROM participations").fetchone()[0]
        n_join = conn.execute(
            "SELECT COUNT(*) FROM events WHERE json_extract(data,'$.type')='UnitJoining'"
        ).fetchone()[0]
        n_nam = conn.execute(
            "SELECT COUNT(*) FROM events WHERE json_extract(data,'$.type')='UnitNaming'"
        ).fetchone()[0]

    print()
    print('═' * 55)
    print(f"DB-Gesamt: {a} Actors | {e} Events | {p} Participations")
    print(f"           davon UnitJoining: {n_join}  |  UnitNaming: {n_nam}")
    print()

    # ─── Test: verorte unit_20_pz_gren_div August 1943 ─────────────────────────
    print('═' * 55)
    print("TEST: verorte('unit_20_pz_gren_div', '1943-08')")
    results = db.verorte("unit_20_pz_gren_div", "1943-08")
    if not results:
        print("  ✗  KEINE ERGEBNISSE")
    else:
        for r in results[:3]:
            place = r.get("place") or {}
            src = r.get("source") or {}
            print(f"  {r['id']}  ort={place.get('name','—')}  "
                  f"certainty={src.get('certainty')}  source={src.get('type')}")
        found_orel = any(
            'orel' in (r.get('place') or {}).get('name', '').lower()
            or 'orel' in (r.get('notes') or '').lower()
            for r in results
        )
        print(f"  {'✓' if found_orel else '✗'}  Orel-Raum {'gefunden' if found_orel else 'NICHT GEFUNDEN'}")


if __name__ == '__main__':
    run()
