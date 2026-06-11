"""
abbreviations.py — Abkürzungsauflösung für WASt-Dokumente.

Öffentliche API:
  load_abbreviations()               → dict {abkürzung: auflösung}
  resolve_abbreviations(text)        → dict mit found / unresolved
  add_user_abbreviation(abbrev, aufl)→ None (persistiert in JSON)
"""

import json
import re
from pathlib import Path

ABBREV_FILE = Path(__file__).parent / "wast_abbreviations.json"


def load_abbreviations() -> dict[str, str]:
    """Lädt alle Abkürzungen (Kategorien + benutzerdefiniert) als flache Tabelle."""
    data = json.loads(ABBREV_FILE.read_text(encoding="utf-8"))
    lookup: dict[str, str] = {}
    for kategorie in data["kategorien"].values():
        lookup.update(kategorie)
    lookup.update(data.get("benutzerdefiniert", {}))
    return lookup


def resolve_abbreviations(text: str) -> dict:
    """
    Findet alle bekannten Abkürzungen im Text und löst sie auf.

    Rückgabe:
      text_original  — unveränderter Eingabetext
      found          — {abkürzung: auflösung} für alle Treffer
      unresolved     — Liste unbekannter Abkürzungsmuster (Großbuchstabe + Punkt)
    """
    lookup = load_abbreviations()
    found: dict[str, str] = {}

    # Längste Abkürzungen zuerst — verhindert Partial-Match (z.B. "Verl." vor "Gr.Spli.Verl.")
    for abbrev in sorted(lookup.keys(), key=len, reverse=True):
        if abbrev in text:
            found[abbrev] = lookup[abbrev]

    # Potenzielle unbekannte Abkürzungen: Großbuchstabe(n) + Punkt(e)
    potential = re.findall(
        r'\b[A-ZÄÖÜ][a-zäöü]*\.(?:[A-ZÄÖÜ][a-zäöü]*\.)*',
        text,
    )
    unresolved = list({p for p in potential if p not in found and p not in lookup})

    return {
        "text_original": text,
        "found": found,
        "unresolved": unresolved,
    }


def add_user_abbreviation(abbrev: str, aufloesung: str) -> None:
    """Fügt eine benutzerdefinierte Abkürzung dauerhaft zur JSON-Datei hinzu."""
    data = json.loads(ABBREV_FILE.read_text(encoding="utf-8"))
    data["benutzerdefiniert"][abbrev] = aufloesung
    ABBREV_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
