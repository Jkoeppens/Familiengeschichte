"""
entity_linking.py — verknüpft extrahierte Einheitsnamen und Personennamen
mit Actors in familiengeschichte.db.

Öffentliche API:
  link_unit(einheit_name, jahr)              → dict
  link_person(name, birth_date)              → str
  link_all(extraction_result)                → dict
  get_current_unit(person_id, zeitpunkt)     → dict|None
  resolve_location(person_id, zeitpunkt)     → dict
"""

import json
import re
from datetime import date
from typing import Optional

from rapidfuzz import fuzz, process

import db
from abbreviations import load_abbreviations

_ABBREVS: dict[str, str] = load_abbreviations()

# ─── Konfiguration ────────────────────────────────────────────────────────────

# Normalisierungspaare — beide Richtungen (vollständiger Name ↔ Abkürzung)
UNIT_NORMALIZATIONS: dict[str, str] = {
    "Nachrichten-Abteilung":         "N.A.",
    "Nachrichten-Ersatz-Abteilung":  "N.E.A.",
    "Infanterie-Regiment":           "I.R.",
    "Panzergrenadier-Regiment":      "Pz.Gren.Rgt.",
    "Grenadier-Regiment":            "Gren.Rgt.",
    "Grenadier-Ersatz-Bataillon":    "G.E.B.",
    # Umgekehrt
    "N.A.":           "Nachrichten-Abteilung",
    "N.E.A.":         "Nachrichten-Ersatz-Abteilung",
    "I.R.":           "Infanterie-Regiment",
    "Pz.Gren.Rgt.":   "Panzergrenadier-Regiment",
    "Gren.Rgt.":      "Grenadier-Regiment",
    "G.E.B.":         "Grenadier-Ersatz-Bataillon",
    "Gren.Ers.Btl.":  "Grenadier-Ersatz-Bataillon",
    # Tessin-Kurzformen (nicht im WASt-Standard, aber häufig in Dokumenten)
    "Nachr.-Abt.":    "Nachrichten-Abt.",
    "Nachr.Abt.":     "Nachrichten-Abt.",
}

# Sub-Einheits-Präfix: "1. Kompanie", "Stamm-Kp.", "1. Genesenden-Kompanie", "Marsch-Kp." …
_SUBUNIT_RE = re.compile(
    r'^(?:\d+\.\s+)?(?:(?:[A-ZÄÖÜa-zäöüß]+-)+)?'
    r'(?:Kompanie|Kp\.|Zug|Stab|Batterie|Schwadron)\s+',
)

_FUZZY_THRESHOLD = 88


def _expand_label(pref: str) -> list[str]:
    """Generiert Suchvarianten aus pref_label zur Laufzeit (Fallback wenn alt_labels leer).

    Behandelt zwei Fälle:
    - "20. Nachrichten-Abt.20" → Trailing-Nummer strippen → expandieren → Varianten
    - "20. Nachrichten-Abt."   → direkt expandieren → Varianten
    """
    variants: set[str] = set()
    m = re.match(r'^(\d+)\.\s+(.+)$', pref)
    if not m:
        expanded = pref
        for abk, lang in _ABBREVS.items():
            expanded = expanded.replace(abk, lang)
        if expanded != pref:
            variants.add(expanded)
        return list(variants)

    num, name = m.group(1), m.group(2)

    # Trailing-Nummer aus name strippen: "Nachrichten-Abt.20" → "Nachrichten-Abt."
    # \b greift zwischen "." (non-word) und Ziffer (word) → korrekt für "Abt.20"
    name_clean = re.sub(r'\s*\b' + re.escape(num) + r'\s*$', '', name).rstrip()

    # Abkürzungen expandieren: "Nachrichten-Abt." → "Nachrichten-Abteilung"
    name_exp = name_clean
    for abk, lang in _ABBREVS.items():
        name_exp = name_exp.replace(abk, lang)

    for n in dict.fromkeys([name_clean, name_exp]):  # Reihenfolge, kein Duplikat
        variants.add(f"{num}. {n}")   # "20. Nachrichten-Abt." / "20. Nachrichten-Abteilung"
        variants.add(f"{n} {num}")    # "Nachrichten-Abt. 20"  / "Nachrichten-Abteilung 20"

    variants.discard(pref)
    return [v for v in variants if len(v) >= 4]


# ─── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _strip_subunit(name: str) -> str:
    """Entfernt führenden Sub-Einheits-Bezeichner.
    '1. Kompanie Nachrichten-Abteilung 20' → 'Nachrichten-Abteilung 20'
    'Stamm-Kompanie Nachrichten-Ersatz-Abteilung 20' → 'Nachrichten-Ersatz-Abteilung 20'
    """
    return _SUBUNIT_RE.sub("", name).strip()


def _normalized_variants(name: str) -> list[str]:
    """Erzeugt normalisierte Varianten via UNIT_NORMALIZATIONS (beide Richtungen)."""
    variants: set[str] = set()
    for src, dst in UNIT_NORMALIZATIONS.items():
        if src in name:
            variants.add(name.replace(src, dst))
    return list(variants)


def _make_person_id(family: str, given: str, year: Optional[str]) -> str:
    def _norm(s: str) -> str:
        s = s.lower()
        for a, b in [("ü", "ue"), ("ö", "oe"), ("ä", "ae"), ("ß", "ss")]:
            s = s.replace(a, b)
        return re.sub(r"[^a-z0-9]", "", s)
    fam = _norm(family)
    parts = re.split(r"[\s\-]+", given)
    initials = "".join(_norm(p)[0] for p in parts if p and _norm(p))
    return f"person_{fam}_{initials}_{year}" if year else f"person_{fam}_{initials}"


# ─── Unit-Index ───────────────────────────────────────────────────────────────

def _load_unit_index() -> list[tuple[str, str, list[str]]]:
    """Alle MilitaryUnit-Actors als [(id, pref_label, alle_labels)]."""
    with db._get_conn() as conn:
        rows = conn.execute(
            "SELECT id, pref_label, data FROM actors WHERE type='MilitaryUnit'"
        ).fetchall()
    db_entries: list[tuple] = []
    for row in rows:
        data = json.loads(row["data"])
        alts = list(data.get("alt_labels", []))
        if not alts:
            alts = _expand_label(row["pref_label"])
        # Leerzeichen zwischen Buchstabe und Ziffer normalisieren ("Regiment90" → "Regiment 90")
        alts = [re.sub(r'([a-zäöüß])(\d)', r'\1 \2', a) for a in alts]
        db_entries.append((row["id"], row["pref_label"], alts))
    return db_entries


def _flat_labels(units: list[tuple]) -> list[tuple[str, str]]:
    """Flache [(uid, label)] Liste für alle Pref- und Alt-Labels."""
    out: list[tuple[str, str]] = []
    for uid, pref, alts in units:
        out.append((uid, pref))
        for alt in alts:
            out.append((uid, alt))
    return out


# ─── 1. link_unit ─────────────────────────────────────────────────────────────

def link_unit(einheit_name: str, jahr: int) -> dict:
    """
    Sucht die beste Übereinstimmung für einen Einheitsnamen in der DB.

    Reihenfolge:
    1. Exakter Match auf pref_label oder alt_labels (inkl. historischer Redesignierungen)
    2. Normalisierter Match nach Sub-Einheits-Präfix-Entfernung → exakter Match
    3. Normalisierter Match via UNIT_NORMALIZATIONS → exakter Match
    4. Fuzzy Match (rapidfuzz WRatio ≥ 85)
    5. Kein Match

    Gibt zurück:
    {
        "actor_id":       str|None,
        "pref_label":     str|None,
        "match_type":     "exact"|"normalized"|"fuzzy"|"none",
        "confidence":     0.0–1.0,
        "tessin_standort": dict|None   # erster Treffer aus verorte(uid, str(jahr))
    }
    """
    units = _load_unit_index()
    # OCR-Fragmente und Zombie-Actors herausfiltern: pref_label < 8 Zeichen sind
    # nie valide Treffer (z.B. 'Div.', 'Kp.', 'U:') und verursachen falsche
    # partial_ratio=100-Matches durch Substring-Effekte.
    units = [u for u in units if len(u[1]) >= 8]
    labels = _flat_labels(units)

    pref_by_id = {u[0]: u[1] for u in units}

    def _hit(uid: str, mtype: str, conf: float) -> dict:
        standort = db.verorte(uid, str(jahr))
        if not standort:
            # Fallback: Parent-Einheit (Rgt. → Division) für bessere Verortung
            with db._get_conn() as conn:
                row = conn.execute(
                    "SELECT json_extract(data, '$.parent_unit_id') FROM actors WHERE id = ?",
                    (uid,),
                ).fetchone()
            parent_id = row[0] if row else None
            if parent_id:
                standort = db.verorte(parent_id, str(jahr))
        return {
            "actor_id":        uid,
            "pref_label":      pref_by_id.get(uid, uid),
            "match_type":      mtype,
            "confidence":      conf,
            "tessin_standort": standort[0] if standort else None,
        }

    # Schritt 1: Exakter Match (pref_label oder alt_label)
    for uid, label in labels:
        if einheit_name == label:
            return _hit(uid, "exact", 1.0)

    # Schritt 2: Sub-Einheits-Präfix entfernen → exakter Match
    stripped = _strip_subunit(einheit_name)
    if stripped != einheit_name:
        for uid, label in labels:
            if stripped == label:
                return _hit(uid, "normalized", 0.95)

    # Schritt 3: UNIT_NORMALIZATIONS auf Original und gestrippten Namen
    for base in dict.fromkeys([einheit_name, stripped]):  # dedupliziert, Reihenfolge erhalten
        for variant in _normalized_variants(base):
            for uid, label in labels:
                if variant == label:
                    return _hit(uid, "normalized", 0.90)

    # Schritt 4: Fuzzy Match
    flat_text = [label for _, label in labels]
    best_uid: Optional[str] = None
    best_score = 0.0

    for query in dict.fromkeys([einheit_name, stripped]):
        hits = process.extract(query, flat_text, scorer=fuzz.WRatio, limit=5)
        for _label, score, idx in hits:
            if score >= _FUZZY_THRESHOLD and score > best_score:
                best_score = score
                best_uid = labels[idx][0]

    if best_uid:
        return _hit(best_uid, "fuzzy", best_score / 100)

    return {
        "actor_id":        None,
        "pref_label":      None,
        "match_type":      "none",
        "confidence":      0.0,
        "tessin_standort": None,
    }


# ─── 2. link_person ───────────────────────────────────────────────────────────

def link_person(name: str, birth_date: str) -> str:
    """
    Sucht Person per family_name + birth_date. Legt neuen Actor an falls nicht gefunden.
    Gibt actor_id zurück.
    """
    if "," in name:
        family, given = [p.strip() for p in name.split(",", 1)]
    else:
        family, given = name.strip(), ""

    with db._get_conn() as conn:
        row = conn.execute(
            """
            SELECT id FROM actors
            WHERE type='Person'
              AND json_extract(data, '$.family_name') = ?
              AND json_extract(data, '$.birth_date')  = ?
            """,
            (family, birth_date),
        ).fetchone()

    if row:
        return row["id"]

    year = birth_date[:4] if birth_date and len(birth_date) >= 4 else None
    actor_id = _make_person_id(family, given, year)
    db.insert_actor({
        "id":          actor_id,
        "type":        "Person",
        "pref_label":  name,
        "alt_labels":  [],
        "family_name": family,
        "given_name":  given or None,
        "birth_date":  birth_date or None,
        "created_at":  date.today().isoformat(),
    })
    return actor_id


# ─── 3. link_all ──────────────────────────────────────────────────────────────

def link_all(extraction_result: dict) -> dict:
    """
    Verknüpft alle Personen und Einheiten in einem Extraktionsergebnis mit DB-Actors.
    Unterstützt Bundesarchiv-Format (persons) und WASt-Format (pages).
    Gibt vollständig verlinktes Dict zurück, bereit für DB-Insert.
    """
    result = dict(extraction_result)

    # Bundesarchiv-Format: extraction_result["persons"]
    if "persons" in result:
        linked_persons = []
        for person in result["persons"]:
            p = dict(person)
            if p.get("name") and p.get("birth_date"):
                p["linked_actor_id"] = link_person(p["name"], p["birth_date"])

            linked_ems = []
            for em in p.get("einheitsmeldungen", []):
                e = dict(em)
                unit = link_unit(e["einheit"], e["jahr"])
                e["actor_id"]        = unit["actor_id"]
                e["unit_match_type"] = unit["match_type"]
                e["unit_confidence"] = unit["confidence"]
                e["tessin_standort"] = unit["tessin_standort"]
                linked_ems.append(e)
            p["einheitsmeldungen"] = linked_ems
            linked_persons.append(p)
        result["persons"] = linked_persons

    # WASt-Format: extraction_result["pages"]
    if "pages" in result:
        linked_pages = []
        for page in result["pages"]:
            p = dict(page)
            linked_meldungen = []
            for m in p.get("meldungen", []):
                e = dict(m)
                if e.get("einheit"):
                    datum_iso = e.get("datum_iso", "")
                    jahr = int(datum_iso[:4]) if datum_iso and datum_iso[:4].isdigit() else 1940
                    unit = link_unit(e["einheit"], jahr)
                    e["actor_id"]        = unit["actor_id"]
                    e["unit_match_type"] = unit["match_type"]
                    e["unit_confidence"] = unit["confidence"]
                linked_meldungen.append(e)
            p["meldungen"] = linked_meldungen
            linked_pages.append(p)
        result["pages"] = linked_pages

    return result


# ─── 4. get_current_unit ──────────────────────────────────────────────────────

def get_current_unit(person_id: str, zeitpunkt: str) -> Optional[dict]:
    """
    Findet die Einheit der Person zu zeitpunkt anhand von PersonJoining-Events.

    Reihenfolge:
    1. PersonJoining-Events, die zeitpunkt überlappen
    2. Fallback: neuestes PersonJoining-Event vor zeitpunkt (time_begin <= zeitpunkt_begin)

    Gibt link_unit-Ergebnis zurück, oder None wenn kein Joining-Event gefunden.
    """
    z_begin, z_end = db._zeitpunkt_range(zeitpunkt)

    with db._get_conn() as conn:
        # Schritt 1: überlappende PersonJoining-Events
        rows = conn.execute(
            """
            SELECT e.data
            FROM events e
            JOIN participations p ON e.id = p.event_id
            WHERE p.actor_id = ?
              AND e.type = 'PersonJoining'
              AND (e.time_begin IS NULL OR e.time_begin <= ?)
              AND (e.time_end   IS NULL OR e.time_end   >= ?)
            ORDER BY json_extract(e.data, '$.source.certainty') DESC
            LIMIT 1
            """,
            (person_id, z_end, z_begin),
        ).fetchall()

        if not rows:
            # Schritt 2: neuestes PersonJoining-Event vor zeitpunkt
            rows = conn.execute(
                """
                SELECT e.data
                FROM events e
                JOIN participations p ON e.id = p.event_id
                WHERE p.actor_id = ?
                  AND e.type = 'PersonJoining'
                  AND e.time_begin <= ?
                ORDER BY e.time_begin DESC
                LIMIT 1
                """,
                (person_id, z_begin),
            ).fetchall()

    if not rows:
        return None

    event_data = json.loads(rows[0]["data"])
    label = event_data.get("label", "")

    # Label-Format: "Name bei Einheit"
    if " bei " not in label:
        return None

    einheit_name = label.split(" bei ", 1)[1].strip()
    # Jahr aus Zeitpunkt extrahieren
    jahr = int(z_begin[:4]) if z_begin and z_begin[:4].isdigit() else 1940
    return link_unit(einheit_name, jahr)


# ─── 5. resolve_location ──────────────────────────────────────────────────────

def resolve_location(person_id: str, zeitpunkt: str) -> dict:
    """
    Zentrale Verortungsfunktion — führt alle Quellen nach Priorität zusammen.

    Rückgabe:
    {
        "lat":        float|None,
        "lon":        float|None,
        "place_name": str|None,
        "certainty":  int (0–5),
        "sicherheit": "belegt"|"einheit"|"unbekannt",
        "source":     dict|None,
        "event_id":   str|None,
    }

    Stufe 1 — Direkt belegter Standort (certainty ≥ 4, generated_by = "direkt"):
      Wählt das Event mit höchster certainty, bevorzugt solche mit Koordinaten.

    Stufe 2 — Einheitsstandort (PersonJoining → Tessin-DB):
      Ermittelt aktuelle Einheit via get_current_unit, fragt deren Standort ab.

    Stufe 3 — Unbekannt.
    """
    # Stufe 1: direkt belegte Ereignisse
    events = db.verorte(person_id, zeitpunkt)
    direct = [
        e for e in events
        if e.get("source", {}).get("certainty", 0) >= 4
        and e.get("source", {}).get("generated_by") == "direkt"
        # Undatierte Events (begin=None UND end=None) matchen via SQL jeden Zeitpunkt —
        # sie sollen für datumsspezifische Abfragen aber nicht als "belegt" gelten.
        and (
            e.get("time_span", {}).get("begin") is not None
            or e.get("time_span", {}).get("end") is not None
        )
    ]

    if direct:
        # Sort: cert DESC, hat Koordinaten DESC, time_begin ASC (frühestes = laufendes Ereignis)
        # NULL-begin → "0000" → sortiert vor allen datierten → bevorzugt offene Zeiträume
        direct.sort(key=lambda e: (
            -e.get("source", {}).get("certainty", 0),
            0 if (e.get("place") or {}).get("lat") is not None else 1,
            e.get("time_span", {}).get("begin") or "0000",
        ))
        best = direct[0]
        place = best.get("place") or {}
        return {
            "lat":        place.get("lat"),
            "lon":        place.get("lon"),
            "place_name": place.get("name"),
            "certainty":  best["source"]["certainty"],
            "sicherheit": "belegt",
            "source":     best.get("source"),
            "event_id":   best.get("id"),
        }

    # Stufe 2: Einheitsstandort über PersonJoining → Tessin
    unit = get_current_unit(person_id, zeitpunkt)
    if unit and unit.get("actor_id"):
        unit_events = db.verorte(unit["actor_id"], zeitpunkt)
        if unit_events:
            best_unit = unit_events[0]
            place = best_unit.get("place") or {}
            if place.get("lat") is not None:
                return {
                    "lat":        place.get("lat"),
                    "lon":        place.get("lon"),
                    "place_name": place.get("name"),
                    "certainty":  2,
                    "sicherheit": "einheit",
                    "source":     best_unit.get("source"),
                    "event_id":   best_unit.get("id"),
                }

    # Stufe 3: unbekannt
    return {
        "lat":        None,
        "lon":        None,
        "place_name": None,
        "certainty":  0,
        "sicherheit": "unbekannt",
        "source":     None,
        "event_id":   None,
    }
