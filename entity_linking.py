"""
entity_linking.py — verknüpft extrahierte Einheitsnamen und Personennamen
mit Actors in familiengeschichte.db.

Öffentliche API:
  link_unit(einheit_name, jahr)  → dict
  link_person(name, birth_date)  → str
  link_all(extraction_result)    → dict
"""

import json
import re
from datetime import date
from typing import Optional

from rapidfuzz import fuzz, process

import db

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
    "N.A.":          "Nachrichten-Abteilung",
    "N.E.A.":        "Nachrichten-Ersatz-Abteilung",
    "I.R.":          "Infanterie-Regiment",
    "Pz.Gren.Rgt.":  "Panzergrenadier-Regiment",
    "Gren.Rgt.":     "Grenadier-Regiment",
    "G.E.B.":        "Grenadier-Ersatz-Bataillon",
    "Gren.Ers.Btl.": "Grenadier-Ersatz-Bataillon",
}

# Historisch belegte Vorgänger-/Nachfolgebezeichnungen die im Tessin-DB fehlen.
# Einheiten wurden 1942/43 oft von Infanterie- zu Panzergrenadier-Regimentern
# redesigniert; WASt-Karten verwenden noch die alte Bezeichnung.
_ALT_LABEL_OVERRIDES: dict[str, list[str]] = {
    "unit_pzgrenrgt90": ["Infanterie-Regiment 90"],  # Redesigniert 1942
}

# Sub-Einheits-Präfix: "1. Kompanie", "Stamm-Kompanie", "1. Genesenden-Kompanie" …
_SUBUNIT_RE = re.compile(
    r'^(?:\d+\.\s+)?(?:[A-ZÄÖÜa-zäöüß]+-)?'
    r'(?:Kompanie|Zug|Stab|Batterie|Schwadron)\s+',
)

_FUZZY_THRESHOLD = 85


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
    result = []
    for row in rows:
        data = json.loads(row["data"])
        alts = list(data.get("alt_labels", []))
        alts += _ALT_LABEL_OVERRIDES.get(row["id"], [])
        result.append((row["id"], row["pref_label"], alts))
    return result


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
    labels = _flat_labels(units)

    pref_by_id = {u[0]: u[1] for u in units}

    def _hit(uid: str, mtype: str, conf: float) -> dict:
        standort = db.verorte(uid, str(jahr))
        return {
            "actor_id":        uid,
            "pref_label":      pref_by_id[uid],
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
