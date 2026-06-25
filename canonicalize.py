"""
Zentrale Kanonisierungsfunktion für Militäreinheiten.

Prinzip: Jede Einheit hat genau eine kanonische Form:
  Langform + arabische Zahl
  "N.A. 20"              → "Nachrichten-Abteilung 20"
  "Nachrichten-Abt. 20"  → "Nachrichten-Abteilung 20"
  "Nachr.Abt.20"         → "Nachrichten-Abteilung 20"

Daraus wird die ID gebaut:
  "Nachrichten-Abteilung 20" → "unit_20_nachrichten_abteilung"

Einzige Quelle der Wahrheit: wast_abbreviations.json (kategorien.einheiten)
"""

import re
import json
from pathlib import Path


def _load_abbrevs() -> dict[str, str]:
    p = Path(__file__).parent / "wast_abbreviations.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    return data["kategorien"]["einheiten"]


ABBREVS: dict[str, str] = _load_abbrevs()

# Längste Abkürzung zuerst → verhindert Teilersetzungen ("N.A." vor "A.")
_ABBREVS_SORTED = sorted(ABBREVS.items(), key=lambda x: -len(x[0]))


def _strip_number(name: str, nummer: str) -> str:
    """Entfernt Nummer aus Einheitsnamen, egal ob führend, trailing oder eingebettet."""
    # Führend mit Punkt: "20. Pz.Gren.Div." → "Pz.Gren.Div."
    name = re.sub(r'^\s*' + re.escape(nummer) + r'\.\s*', '', name)
    # Trailing mit oder ohne Leerzeichen: "Abt. 20", "Abt.20"
    name = re.sub(r'\s*\b' + re.escape(nummer) + r'\s*$', '', name)
    return name.strip()


def kanonisiere(name: str) -> str:
    """
    Wandelt beliebige Schreibweise in kanonische Form um.

    "N.A. 20"             → "Nachrichten-Abteilung 20"
    "20. Pz.Gren.Div."    → "Panzergrenadier-Division 20"
    "Nachr.Abt.20"        → "Nachrichten-Abteilung 20"
    """
    name = name.strip()

    # 1. Nummer extrahieren (erste vorkommende ganze Zahl)
    m = re.search(r'\b(\d+)\b', name)
    nummer = m.group(1) if m else None

    # 2. Nummer aus Namen entfernen
    name_clean = _strip_number(name, nummer) if nummer else name

    # 3. Abkürzungen expandieren (längste zuerst verhindert "Abt." vor "Nachr.Abt.")
    for abk, lang in _ABBREVS_SORTED:
        name_clean = name_clean.replace(abk, lang)

    name_clean = name_clean.strip(' .')

    # 4. Kanonische Form: Langname + Leerzeichen + Nummer
    if nummer:
        return f"{name_clean} {nummer}"
    return name_clean


def make_id(kanonisch: str) -> str:
    """
    Baut DB-ID aus kanonischer Form.

    "Nachrichten-Abteilung 20"  → "unit_20_nachrichten_abteilung"
    "Panzergrenadier-Division 20" → "unit_20_panzergrenadier_division"
    "Infanterie-Regiment 90"    → "unit_90_infanterie_regiment"
    """
    m = re.search(r'\b(\d+)\b', kanonisch)
    nummer = m.group(1) if m else None

    name = re.sub(r'\s*\b\d+\b\s*', ' ', kanonisch).strip()

    # Umlaute → ASCII (für DB-IDs)
    for von, nach in [('ä', 'ae'), ('ö', 'oe'), ('ü', 'ue'), ('ß', 'ss'),
                      ('Ä', 'ae'), ('Ö', 'oe'), ('Ü', 'ue')]:
        name = name.replace(von, nach)

    # Nur Buchstaben und Leerzeichen → underscore-getrennt
    name = re.sub(r'[^a-zA-Z\s]', ' ', name)
    name = '_'.join(name.lower().split())

    if nummer:
        return f"unit_{nummer}_{name}"
    return f"unit_{name}"
