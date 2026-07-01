#!/usr/bin/env python3
"""
load_hierarchy.py — 2.3 Einheitshierarchie aus Gliederungsfeldern

Liest gliederung UND ueberstellung_kurz aus allen Tessin-Bänden,
extrahiert Über-/Unterordnungsbeziehungen, legt UnitJoining-Events an
und setzt parent_unit_id auf den Child-Actors.
"""

import json
import re
import sys
import glob
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))
import db

CREATED = "2026-06-11"

# ─── Label-Normalisierung ──────────────────────────────────────────────────────

_ABBREVS = [
    ('Inf.Div.', 'Infanterie-Division'),
    ('Pz.Gren.Div.', 'Panzergrenadier-Division'),
    ('Pz.Gren.Rgt.', 'Panzergrenadier-Regiment'),
    ('Pz.Rgt.', 'Panzer-Regiment'),
    ('Pz.Div.', 'Panzer-Division'),
    ('Pz.Abt.', 'Panzer-Abteilung'),
    ('Inf.Rgt.', 'Infanterie-Regiment'),
    ('Inf.Btl.', 'Infanterie-Bataillon'),
    ('Art.Rgt.', 'Artillerie-Regiment'),
    ('Art.Abt.', 'Artillerie-Abteilung'),
    ('Pi.Btl.', 'Pionier-Bataillon'),
    ('Nachr.Abt.', 'Nachrichten-Abteilung'),
    ('Auf.Abt.', 'Aufklärungs-Abteilung'),
    ('Kav.', 'Kavallerie-'),
    ('Geb.', 'Gebirgs-'),
    ('Div.', 'Division'),
    ('Rgt.', 'Regiment'),
    ('Btl.', 'Bataillon'),
    ('Abt.', 'Abteilung'),
    ('Kp.', 'Kompanie'),
    ('Inf.', 'Infanterie-'),
    ('Pz.', 'Panzer-'),
    ('Gren.', 'Grenadier-'),
    ('Art.', 'Artillerie-'),
    ('Pi.', 'Pionier-'),
    ('Nachr.', 'Nachrichten-'),
    ('Aufkl.', 'Aufklärungs-'),
    ('mot.', '(mot.)'),
    ('(mot)', '(mot.)'),
]

_TYPE_SYNONYMS = {
    'infanterie': ['inf', 'inf.', 'infanter'],
    'panzergrenadier': ['pz.gren', 'pzgren', 'panzergren', 'gren.', 'grenadier'],
    'panzer': ['pz', 'pz.'],
    'artillerie': ['art', 'art.'],
    'pionier': ['pi', 'pi.'],
    'nachrichten': ['nachr', 'nachr.'],
    'aufklaerung': ['aufkl', 'aufkl.', 'aufklaerungs'],
    'division': ['div', 'div.'],
    'regiment': ['rgt', 'rgt.', 'regt.'],
    'bataillon': ['btl', 'btl.', 'bat.'],
    'abteilung': ['abt', 'abt.'],
    'kompanie': ['kp', 'kp.'],
    'kavallerie': ['kav', 'kav.'],
    'gebirgs': ['geb', 'geb.'],
    'volksgrenadier': ['volks-gren', 'volksgren', 'vg'],
}


def _normalize_label(s: str) -> str:
    """Normiert Label für Vergleich: Lowercase, Umlaute, Leerzeichen."""
    s = s.strip()
    for ger, lat in [('ä','ae'),('ö','oe'),('ü','ue'),('ß','ss')]:
        s = s.replace(ger, lat)
    s = s.lower()
    s = re.sub(r'[.()\-/,]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _expand_abbrevs(s: str) -> str:
    for short, full in _ABBREVS:
        s = s.replace(short, full)
    return s


# ─── Akteur-Index aufbauen ─────────────────────────────────────────────────────

def build_actor_index() -> tuple[dict, dict]:
    """
    Gibt zurück:
      label_index: normalized_label → actor_id
      num_type_index: (number_str, type_keyword) → [actor_id, ...]
    """
    label_index: dict[str, str] = {}
    num_type_index: dict[tuple, list] = defaultdict(list)

    with db._get_conn() as conn:
        rows = conn.execute(
            "SELECT id, data FROM actors WHERE type = 'MilitaryUnit'"
        ).fetchall()

    for row in rows:
        actor_data = json.loads(row["data"])
        actor_id = actor_data["id"]
        labels = [actor_data.get("pref_label", "")] + (actor_data.get("alt_labels") or [])

        for lbl in labels:
            if not lbl:
                continue
            # Full label index (normalized)
            norm = _normalize_label(lbl)
            if norm:
                label_index[norm] = actor_id
            # Also with expanded abbreviations
            norm_exp = _normalize_label(_expand_abbrevs(lbl))
            if norm_exp and norm_exp != norm:
                label_index[norm_exp] = actor_id
            # (number, type) index
            nt = _extract_num_type(lbl)
            if nt:
                if actor_id not in num_type_index[nt]:
                    num_type_index[nt].append(actor_id)

    return label_index, dict(num_type_index)


_TYPE_KEYWORDS = [
    'panzergrenadier', 'volksgrenadier', 'gebirgs',
    'infanterie', 'kavallerie', 'artillerie', 'pionier', 'nachrichten',
    'aufklaer', 'panzer', 'grenadier', 'jaeger',
]

_TYPE_ABBR = {
    'pz.gren': 'panzergrenadier', 'pzgren': 'panzergrenadier',
    'volks-gren': 'volksgrenadier', 'volksgren': 'volksgrenadier',
    'inf': 'infanterie', 'art': 'artillerie', 'pi': 'pionier',
    'nachr': 'nachrichten', 'aufkl': 'aufklaer', 'pz': 'panzer',
    'gren': 'grenadier', 'kav': 'kavallerie', 'geb': 'gebirgs',
}


def _extract_num_type(label: str) -> tuple[str, str] | None:
    """Extrahiert (nummer, typ_schlüssel) aus Einheitsname."""
    m = re.search(r'(\d+)', label)
    if not m:
        return None
    num = m.group(1)
    low = _normalize_label(label)
    # Try expanded type first
    for kw in _TYPE_KEYWORDS:
        if kw in low:
            return (num, kw)
    # Try abbreviations
    for abbr, kw in _TYPE_ABBR.items():
        if abbr in low:
            return (num, kw)
    return None


# ─── Einheitenname matchen ─────────────────────────────────────────────────────

def match_unit_name(name: str,
                    label_index: dict,
                    num_type_index: dict) -> str | None:
    """Versucht actor_id zu finden. Gibt None bei keinem Match."""
    name = name.strip()
    if not name or len(name) < 3:
        return None

    # 1. Exakter normalisierter Label-Match
    norm = _normalize_label(name)
    if norm in label_index:
        return label_index[norm]

    # 2. Mit expandierten Abkürzungen
    norm_exp = _normalize_label(_expand_abbrevs(name))
    if norm_exp in label_index:
        return label_index[norm_exp]

    # 3. Nummer + Typ-Schlüssel
    nt = _extract_num_type(name)
    if nt:
        candidates = num_type_index.get(nt, [])
        if len(candidates) == 1:
            return candidates[0]
        # Mehrere Kandidaten: versuche den mit ähnlichstem Label
        if candidates:
            for c in candidates:
                if nt[0] in c:  # Nummer ist in der actor_id
                    return c

    return None


# ─── Elterneinheit aus ueberstellung_kurz extrahieren ─────────────────────────

# Einheitsnamen-Präfix: Zahl + Typ-Schlüsselwort(e) + optionaler Zusatz
_UNIT_PREFIX_RE = re.compile(
    r'(\d{1,3}\.?\s*'
    r'(?:(?:Waffen|SS|Luftwaffe|Marine|Lw\.?|Volks|Feld|Res\.?|Sich\.?)[-.\s]*)?'
    r'(?:'
    r'Pz\.Gren\.|Pz\.?Gren\.|Panzergrenadier|'
    r'Inf\.?(?:anterie)?|Pz\.?(?:anzer)?|Gren(?:adier)?\.?|'
    r'Art(?:illerie)?\.?|Pi(?:onier)?\.?|Nachr(?:ichten)?\.?|'
    r'Aufkl\.?|Kav(?:allerie)?\.?|Geb(?:irgs)?\.?|Jäger|Fallsch|Flak|'
    r'Fahr|Fest\.?|Versor|Feldersatz|Feldausbil'
    r')?[-.\s]*'
    r'(?:Div(?:ision)?\.?|Rgt\.?(?:Regt\.?)?|Btl\.?(?:Bataillon)?|'
    r'Abt(?:eilung)?\.?|Kp\.?|AK|Armee(?:korps)?|Korps|Heeresgruppe'
    r')?'
    r'(?:\s*(?:\([^)]{1,30}\)|\.\s*Nr\.\s*\d+))?)',
    re.IGNORECASE,
)

# Explizites "U: <parent>"
_U_EXPLICIT_RE = re.compile(
    r'\bU\s*:\s*([^;*\n]{3,80}?)(?:\s+\*|\s+U2?:|\s*;|$)',
    re.IGNORECASE,
)


def extract_parent_names_from_uk(uk: str) -> list[str]:
    """Extrahiert Elterneinheitsnamen aus ueberstellung_kurz."""
    if not uk:
        return []
    results: list[str] = []

    # 1. Explizite U: … Marker
    for m in _U_EXPLICIT_RE.finditer(uk):
        names_raw = m.group(1)
        # Kann komma-getrennte Liste sein
        for part in re.split(r'[;,]\s*', names_raw):
            p = part.strip().rstrip('.,')
            if p and len(p) > 3 and not re.match(r'^\d{4}$', p):
                results.append(p)

    if results:
        return results

    # 2. Führende Einheitennamen (vor ":" oder Datum oder Ortsangabe)
    # Split bei Stellen wo auf eine klare Einheitsbezeichnung operationale Info folgt
    # Kandidaten: Segmente getrennt durch Leerzeichen + neues Einheitsnamen-Muster
    # Jede parent-Einheit endet bei ": " gefolgt von Jahreszahl oder Ortsnamen
    segments = re.split(
        r'\s{1,3}(?=\d{1,3}\.?\s*(?:'
        r'Pz\.Gren\.|Panzergrenadier|Inf\.?(?:anterie)?|Pz\.?(?:anzer)?|'
        r'Gren(?:adier)?\.?|Art(?:illerie)?\.?|Pi(?:onier)?\.?|Nachr|Kav|Geb)'
        r')',
        uk
    )

    for seg in segments:
        # Trenne bei ": <Jahr/Ort>" oder bei " * <Datum>"
        clean = re.split(r':\s*(?:(?:19|194[0-9]|\d{4})|[A-Z][a-z]{2,})', seg)[0]
        clean = re.split(r'\s+\*', clean)[0]
        clean = clean.strip().rstrip('.,;(')
        if not clean or len(clean) < 4:
            continue
        m = _UNIT_PREFIX_RE.match(clean)
        if m:
            extracted = clean[:len(clean)].strip()
            # Nur sinnvoll lange Namen (nicht nur eine Zahl)
            if len(extracted) > 4 and re.search(r'[A-Za-z]{3,}', extracted):
                results.append(extracted)

    return results[:5]  # Max 5 parent-Kandidaten


# ─── Untereinheiten aus gliederung extrahieren ────────────────────────────────

# Muster für benannte Einheiten (nicht nur Nummernfolgen)
_NAMED_UNIT_RE = re.compile(
    r'(?<!\d)(\d{1,4})\.?\s*'
    r'(?:'
    r'(?:Pz\.Gren\.|Panzergrenadier|Inf\.?(?:anterie)?|Pz\.?(?:anzer)?|'
    r'Gren(?:adier)?\.?|Art(?:illerie)?\.?|Pi(?:onier)?\.?|Nachr(?:ichten)?\.?|'
    r'Aufkl\.?|Kav(?:allerie)?\.?|Geb(?:irgs)?\.?|Jäger|'
    r'Flak|Fest\.?|Sich\.?|Fahr|Versor|San\.?)'
    r'[-.\s]+'
    r'(?:Div(?:ision)?\.?|Rgt\.?(?:Regt\.?)?|Btl\.?(?:Bataillon)?|'
    r'Abt(?:eilung)?\.?|Kp\.?)'
    r'|'
    r'(?:Pz\.Gren\.|Panzergrenadier|Inf\.?(?:anterie)?|Pz\.?(?:anzer)?|'
    r'Gren(?:adier)?\.?|Art(?:illerie)?\.?)'
    r'[-.\s]+(?:Div|Rgt|Btl|Abt)\.'
    r')',
    re.IGNORECASE,
)


def extract_subunits_from_gliederung(gliederung: str) -> list[str]:
    """Extrahiert benannte Untereinheiten aus gliederung-Text."""
    if not gliederung:
        return []
    results = []
    for m in _NAMED_UNIT_RE.finditer(gliederung):
        name = m.group(0).strip().rstrip('.,')
        if name and len(name) > 5:
            results.append(name)
    return results


# ─── Parent-Zeit aus DB holen ─────────────────────────────────────────────────

def get_unit_time_span(actor_id: str) -> tuple[str, str]:
    """Holt min(begin)/max(end) aller UnitJoining-Events des Akteurs."""
    with db._get_conn() as conn:
        row = conn.execute(
            """
            SELECT MIN(e.time_begin), MAX(e.time_end)
            FROM events e
            JOIN participations p ON e.id = p.event_id
            WHERE p.actor_id = ? AND e.type = 'UnitJoining'
            """,
            (actor_id,),
        ).fetchone()
    if row and row[0]:
        # Convert to ISO year-month
        begin = row[0][:7] if row[0] else "1939"
        end = row[1][:7] if row[1] else "1945"
        return begin, end
    return "1939", "1945"


# ─── Hierarchie-Event erzeugen ─────────────────────────────────────────────────

def make_hierarchy_event(child_id: str, parent_id: str,
                          child_label: str, parent_label: str,
                          band: int) -> dict:
    begin, end = get_unit_time_span(parent_id)
    # Verwende Jahres-Präzision für strukturelle Beziehungen
    begin_y = begin[:4]
    end_y = end[:4]

    return {
        "id": f"event_hierarchy_{_id_suffix(child_id)}_{_id_suffix(parent_id)}",
        "type": "UnitJoining",
        "subtype": "Unterstellung",
        "label": f"{child_label} → {parent_label} (Gliederung)",
        "time_span": {
            "begin": begin_y,
            "end": end_y,
            "precision": "year",
        },
        "source": {
            "type": "tessin",
            "certainty": 3,
            "generated_by": "direkt",
            "reference": f"Tessin Bd. {band}",
            "page": None,
        },
        "unit_details": {
            "korps": None,
            "armee": None,
            "heeresgruppe": None,
            "theater": None,
        },
        "notes": f"Hierarchiebeziehung: {child_label} ist Untereinheit von {parent_label}",
        "created_at": CREATED,
    }


def _id_suffix(actor_id: str) -> str:
    return actor_id.removeprefix("unit_")[:30]


def _norm_id(s: str) -> str:
    s = s.lower()
    for a, b in [('ä','ae'),('ö','oe'),('ü','ue'),('ß','ss')]:
        s = s.replace(a, b)
    return re.sub(r'[^a-z0-9]+', '_', s).strip('_')


# ─── Parent_unit_id auf Actor setzen ──────────────────────────────────────────

def set_parent_unit_id(child_id: str, parent_id: str) -> bool:
    """Setzt parent_unit_id wenn noch nicht gesetzt. Gibt True zurück wenn geändert."""
    with db._get_conn() as conn:
        row = conn.execute("SELECT data FROM actors WHERE id = ?", (child_id,)).fetchone()
    if not row:
        return False
    actor = json.loads(row["data"])
    if actor.get("parent_unit_id") is not None:
        return False  # Bereits gesetzt, nicht überschreiben
    actor["parent_unit_id"] = parent_id
    try:
        db.insert_actor(actor)
        return True
    except Exception:
        return False


# ─── Hauptprogramm ─────────────────────────────────────────────────────────────

def run() -> None:
    print("Lade Actor-Index aus DB...")
    label_index, num_type_index = build_actor_index()
    print(f"  {len(label_index)} Label-Einträge, {len(num_type_index)} (Num,Typ)-Einträge\n")

    # Alle bereits bekannten (child, parent) Paare sammeln (aus parent_unit_id)
    with db._get_conn() as conn:
        existing_pairs = {
            (row["id"], json.loads(row["data"]).get("parent_unit_id"))
            for row in conn.execute("SELECT id, data FROM actors").fetchall()
            if json.loads(row["data"]).get("parent_unit_id")
        }

    # Alle DB-Actors für Actor-Lookup
    with db._get_conn() as conn:
        id_to_label: dict[str, str] = {
            row["id"]: json.loads(row["data"]).get("pref_label", row["id"])
            for row in conn.execute("SELECT id, data FROM actors").fetchall()
        }

    new_links:  list[tuple[str, str, int]] = []   # (child_id, parent_id, band)
    not_found:  list[str] = []
    processed_uk_names: set[str] = set()

    files = sorted(
        Path('.').glob('tessin_bd*_final.json'),
        key=lambda p: (int(re.search(r'bd(\d+)', p.stem).group(1)),
                       int(re.search(r'bd\d+-?(\d*)', p.stem).group(1) or 0))
    )

    for fpath in files:
        m = re.search(r'bd(\d+)', fpath.stem)
        band = int(m.group(1)) if m else 0
        data = json.load(fpath.open(encoding='utf-8'))

        for entry in data:
            nummer  = entry.get('nummer', '').strip()
            einheit = entry.get('einheit', '').strip()
            if not einheit or len(einheit) < 4:
                continue
            # Skip offensichtliche OCR-Artefakte (enthalten Klammer am Ende o.ä.)
            if einheit.endswith('(') or re.search(r'[0-9]{4,}', einheit):
                continue

            # Actor-ID des aktuellen Eintrags
            current_id = _make_actor_id_simple(nummer, einheit)

            # ── A) ueberstellung_kurz → Elterneinheit dieses Eintrags
            uk = entry.get('ueberstellung_kurz') or ''
            parent_names = extract_parent_names_from_uk(uk)
            for pname in parent_names:
                if pname in processed_uk_names:
                    continue
                processed_uk_names.add(pname)
                parent_id = match_unit_name(pname, label_index, num_type_index)
                if parent_id and parent_id != current_id:
                    pair = (current_id, parent_id)
                    if pair not in [(c, p) for c, p, _ in new_links]:
                        # Prüfe ob current_id überhaupt in DB ist
                        if current_id in id_to_label:
                            new_links.append((current_id, parent_id, band))
                else:
                    if parent_id is None and len(pname) > 5:
                        not_found.append(pname)

            # ── B) gliederung → Untereinheiten dieses Eintrags
            # Nur für Einheiten auf Division-Ebene oder höher
            current_in_db = id_to_label.get(current_id)
            current_ut = _get_unit_type_from_db(current_id)
            if current_ut in ('Division', 'Korps', 'Armee', 'Heeresgruppe'):
                g = entry.get('gliederung') or ''
                # Nur wenn gliederung kurz genug (lange Texte = OCR-Artefakte)
                if g and len(g) < 500:
                    sub_names = extract_subunits_from_gliederung(g)
                    for sname in sub_names:
                        sub_id = match_unit_name(sname, label_index, num_type_index)
                        if sub_id and sub_id != current_id:
                            pair_g = (sub_id, current_id)
                            if pair_g not in [(c, p) for c, p, _ in new_links]:
                                if current_id in id_to_label:
                                    new_links.append((sub_id, current_id, band))
                        else:
                            if sub_id is None and len(sname) > 5:
                                not_found.append(sname)

    # ─── Dedupliziere ──────────────────────────────────────────────────────────
    seen_pairs: set[tuple] = set()
    unique_links = []
    for child_id, parent_id, band in new_links:
        pair = (child_id, parent_id)
        if pair not in seen_pairs and pair not in existing_pairs:
            seen_pairs.add(pair)
            unique_links.append((child_id, parent_id, band))

    print(f"Hierarchie-Links gefunden:    {len(new_links)} (roh)")
    print(f"Davon neu (nicht dupliziert): {len(unique_links)}")
    print(f"Bereits vorhanden:            {len(existing_pairs)}")

    # ─── Events + Participations einfügen ─────────────────────────────────────
    hier_events = 0
    hier_parts   = 0
    parent_id_set = 0
    errors       = 0

    event_id_counter: dict[str, int] = defaultdict(int)

    for child_id, parent_id, band in unique_links:
        child_label  = id_to_label.get(child_id, child_id)
        parent_label = id_to_label.get(parent_id, parent_id)

        event = make_hierarchy_event(child_id, parent_id,
                                      child_label, parent_label, band)
        eid = event["id"]

        # Eindeutigkeit sichern
        counter = event_id_counter[eid]
        event_id_counter[eid] += 1
        if counter > 0:
            event["id"] = f"{eid}_{counter}"
            eid = event["id"]

        try:
            db.insert_event(event)
            hier_events += 1
        except Exception as exc:
            print(f"  EVENT FEHLER {eid}: {exc}")
            errors += 1
            continue

        for actor_id, role in [(child_id, "subordinate"), (parent_id, "superior")]:
            try:
                db.insert_participation({
                    "event_id": eid,
                    "actor_id": actor_id,
                    "relation": "had_participant",
                    "role": role,
                    "created_at": CREATED,
                })
                hier_parts += 1
            except Exception as exc:
                print(f"  PART FEHLER {eid} {actor_id}: {exc}")
                errors += 1

        # parent_unit_id auf Child setzen
        if set_parent_unit_id(child_id, parent_id):
            parent_id_set += 1

    print(f"\nHierarchie-Events eingefügt:  {hier_events}")
    print(f"Participations eingefügt:     {hier_parts}")
    print(f"parent_unit_id gesetzt:       {parent_id_set}")
    if errors:
        print(f"Fehler:                       {errors}")

    # ─── Statistik ────────────────────────────────────────────────────────────
    with db._get_conn() as conn:
        a = conn.execute("SELECT COUNT(*) FROM actors").fetchone()[0]
        e = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        p = conn.execute("SELECT COUNT(*) FROM participations").fetchone()[0]
        n_hier = conn.execute(
            "SELECT COUNT(*) FROM events "
            "WHERE json_extract(data,'$.subtype')='Unterstellung'"
        ).fetchone()[0]
        n_par = conn.execute(
            "SELECT COUNT(*) FROM actors "
            "WHERE json_extract(data,'$.parent_unit_id') IS NOT NULL "
            "AND type='MilitaryUnit'"
        ).fetchone()[0]

    print(f"\nDB-Gesamt: {a} Actors | {e} Events | {p} Participations")
    print(f"           Hierarchie-Events: {n_hier} | Units mit parent_unit_id: {n_par}")

    # ─── Nicht gefundene (manuelle Lücken) ────────────────────────────────────
    # Dedupliziere und filtere OCR-Artefakte heraus
    not_found_clean = sorted({
        nf for nf in not_found
        if len(nf) > 5
        and re.search(r'[A-Za-z]{3,}', nf)
        and not re.match(r'^[\d\s.,;:]+$', nf)
        and not re.search(r'[0-9]{6,}', nf)  # OCR-Artefakte mit vielen Ziffern
    })[:50]

    print(f"\nNicht gematchte Namen (Stichprobe, max. 50 von {len(not_found)}):")
    for nf in not_found_clean[:50]:
        print(f"  ? {nf}")

    # ─── Test: get_hierarchy ──────────────────────────────────────────────────
    print("\n" + "═" * 55)
    print("TEST: get_hierarchy('unit_pzgrenrgt90')")
    chain = db.get_hierarchy("unit_pzgrenrgt90")
    print(f"  Kette: {chain}")
    if len(chain) >= 2:
        labels = [id_to_label.get(x, x) for x in chain]
        print(f"  Labels: {labels}")
        print("  ✓  Kette bis zur Division gefunden")
    else:
        print("  ✗  Kette zu kurz oder leer")


# ─── Hilfsfunktion: Actor-ID aus Eintrag ──────────────────────────────────────

_KNOWN_IDS: dict[tuple, str] = {
    ('20', 'Infanterie-Division (mot.)'): 'unit_20_pz_gren_div',
    ('20', 'Infanterie-Division (motorisiert)'): 'unit_20_inf_div_mot',
    ('20', 'Panzergrenadier-Division'): 'unit_20_pz_gren_div',
    ('20', 'Nachrichten-Abteilung'): 'unit_na20',
    ('90', 'Grenadier-Regiment'): 'unit_pzgrenrgt90',
    ('90', 'Panzergrenadier-Regiment'): 'unit_pzgrenrgt90',
    ('90', 'Infanterie-Regiment'): 'unit_pzgrenrgt90',
}


def _norm_id_s(s: str) -> str:
    for a, b in [('ä','ae'),('ö','oe'),('ü','ue'),('ß','ss')]:
        s = s.replace(a, b)
    s = re.sub(r'[^a-z0-9]+', '_', s.lower())
    return re.sub(r'_+', '_', s).strip('_')


_unit_type_cache: dict[str, str] = {}


def _get_unit_type_from_db(actor_id: str) -> str:
    if actor_id not in _unit_type_cache:
        with db._get_conn() as conn:
            row = conn.execute(
                "SELECT json_extract(data,'$.unit_type') FROM actors WHERE id = ?",
                (actor_id,)
            ).fetchone()
        _unit_type_cache[actor_id] = row[0] if row and row[0] else "Unknown"
    return _unit_type_cache[actor_id]


def _make_actor_id_simple(nummer: str, einheit: str) -> str:
    key = (nummer.strip(), einheit.strip())
    if key in _KNOWN_IDS:
        return _KNOWN_IDS[key]
    n = _norm_id_s(nummer)
    e = _norm_id_s(einheit)
    return f"unit_{n}_{e}" if n else f"unit_{e}"


if __name__ == '__main__':
    run()
