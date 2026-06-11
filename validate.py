#!/usr/bin/env python3
"""
validate.py — Schema-Validierung für Familiengeschichte-Datenbank

Läuft nach jeder Pipeline-Änderung:
  python3 validate.py

Gibt Exit-Code 0 bei Erfolg, 1 bei Fehlern.
Ausgabe zeigt welche Einträge gegen welche Regeln verstoßen.
"""

import json
import sys
import os
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("jsonschema nicht installiert. Bitte: pip install jsonschema")
    sys.exit(1)

# ─── Konfiguration ────────────────────────────────────────────────────────────

SCHEMA_DIR = Path(__file__).parent / "schema"
DATA_FILES = {
    "actors":         ("actors.json",         "actor.schema.json"),
    "events":         ("events.json",          "event.schema.json"),
    "participations": ("participations.json",  "participation.schema.json"),
}

# Koppermann-Referenzinstanz: diese IDs müssen existieren
REQUIRED_ACTOR_IDS = [
    "person_koppermann_hj_1917",
    "unit_na20",
    "unit_20_inf_div_mot",
    "unit_pzgrenrgt90",
    "unit_20_pz_gren_div",
]

REQUIRED_EVENT_IDS = [
    "event_koppermann_wounding_1943_08_28",
]

# ─── Hilfsfunktionen ─────────────────────────────────────────────────────────

def load_json(path: Path) -> list | dict | None:
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def load_schema(schema_file: str) -> dict:
    path = SCHEMA_DIR / schema_file
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def validate_list(data: list, schema: dict, label: str) -> list[str]:
    """Validiert eine Liste von Objekten gegen ein Schema. Gibt Fehlerliste zurück."""
    errors = []
    validator = jsonschema.Draft7Validator(schema)
    for i, item in enumerate(data):
        item_id = item.get("id", f"[Index {i}]")
        for error in validator.iter_errors(item):
            path = " → ".join(str(p) for p in error.absolute_path) or "(root)"
            errors.append(f"  [{label}] {item_id} | {path}: {error.message}")
    return errors

# ─── Zusätzliche Konsistenzprüfungen ─────────────────────────────────────────

def check_referential_integrity(actors, events, participations) -> list[str]:
    """Prüft ob alle IDs in participations in actors und events existieren."""
    errors = []
    if not actors or not events or not participations:
        return errors

    actor_ids = {a["id"] for a in actors}
    event_ids = {e["id"] for e in events}

    for p in participations:
        if p.get("event_id") not in event_ids:
            errors.append(f"  [Referenz] participation → event_id '{p.get('event_id')}' nicht in events.json")
        if p.get("actor_id") not in actor_ids:
            errors.append(f"  [Referenz] participation → actor_id '{p.get('actor_id')}' nicht in actors.json")

    return errors

def check_required_ids(actors, events) -> list[str]:
    """Prüft ob Koppermann-Referenzinstanzen vorhanden sind."""
    errors = []
    if actors:
        actor_ids = {a["id"] for a in actors}
        for required in REQUIRED_ACTOR_IDS:
            if required not in actor_ids:
                errors.append(f"  [Referenzinstanz] Pflicht-Actor fehlt: {required}")

    if events:
        event_ids = {e["id"] for e in events}
        for required in REQUIRED_EVENT_IDS:
            if required not in event_ids:
                errors.append(f"  [Referenzinstanz] Pflicht-Event fehlt: {required}")

    return errors

def check_date_consistency(events) -> list[str]:
    """Prüft ob begin <= end in time_span."""
    errors = []
    if not events:
        return errors
    for e in events:
        ts = e.get("time_span", {})
        begin = ts.get("begin")
        end = ts.get("end")
        if begin and end and begin > end:
            errors.append(f"  [Datum] {e.get('id')}: begin '{begin}' > end '{end}'")
    return errors

def check_coordinate_consistency(events) -> list[str]:
    """Prüft ob Koordinaten und Präzision konsistent sind."""
    errors = []
    if not events:
        return errors
    for e in events:
        place = e.get("place")
        if not place:
            continue
        precision = place.get("precision")
        lat = place.get("lat")
        lon = place.get("lon")
        radius = place.get("radius_km")

        if precision == "schauplatz":
            if lat is not None or lon is not None:
                errors.append(f"  [Koordinaten] {e.get('id')}: precision=schauplatz aber lat/lon gesetzt")
        elif precision in ("lokalisiert", "stadt", "region"):
            if lat is None or lon is None:
                errors.append(f"  [Koordinaten] {e.get('id')}: precision={precision} aber lat/lon fehlt")
            if radius is None:
                errors.append(f"  [Koordinaten] {e.get('id')}: precision={precision} aber radius_km fehlt")

    return errors

def check_no_duplicate_ids(data: list, label: str) -> list[str]:
    """Prüft auf doppelte IDs."""
    errors = []
    if not data:
        return errors
    seen = {}
    for item in data:
        id_ = item.get("id")
        if id_ is None:
            continue
        if id_ in seen:
            errors.append(f"  [Duplikat] {label}: ID '{id_}' doppelt vorhanden")
        seen[id_] = True
    return errors

# ─── Hauptprogramm ───────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Familiengeschichte-Pipeline — Schema-Validierung")
    print("=" * 60)

    all_errors = []
    loaded = {}

    # 1. JSON-Schema-Validierung
    for name, (data_file, schema_file) in DATA_FILES.items():
        data_path = Path(data_file)
        schema_path = SCHEMA_DIR / schema_file

        if not schema_path.exists():
            print(f"⚠  Schema fehlt: {schema_path}")
            continue

        if not data_path.exists():
            print(f"–  {data_file} nicht gefunden, übersprungen")
            continue

        data = load_json(data_path)
        schema = load_schema(schema_file)

        if not isinstance(data, list):
            all_errors.append(f"  [{name}] Datei muss ein JSON-Array sein")
            continue

        loaded[name] = data
        errors = validate_list(data, schema, name)
        all_errors.extend(errors)

        status = "✓" if not errors else "✗"
        print(f"{status}  {data_file}: {len(data)} Einträge, {len(errors)} Schema-Fehler")

    # 2. Konsistenzprüfungen
    actors = loaded.get("actors")
    events = loaded.get("events")
    participations = loaded.get("participations")

    ref_errors = check_referential_integrity(actors, events, participations)
    all_errors.extend(ref_errors)

    req_errors = check_required_ids(actors, events)
    all_errors.extend(req_errors)

    date_errors = check_date_consistency(events)
    all_errors.extend(date_errors)

    coord_errors = check_coordinate_consistency(events)
    all_errors.extend(coord_errors)

    dup_errors = []
    for name, data in loaded.items():
        dup_errors.extend(check_no_duplicate_ids(data, name))
    all_errors.extend(dup_errors)

    # 3. Ausgabe
    print()
    if all_errors:
        print(f"✗  {len(all_errors)} Fehler gefunden:")
        print()
        for error in all_errors:
            print(error)
        print()
        print("Pipeline gestoppt. Bitte Fehler beheben bevor du weitermachst.")
        sys.exit(1)
    else:
        print("✓  Alle Prüfungen bestanden.")
        print()
        print("Koppermann-Referenzinstanzen vorhanden:")
        if actors:
            actor_ids = {a["id"] for a in actors}
            for req in REQUIRED_ACTOR_IDS:
                status = "✓" if req in actor_ids else "–"
                print(f"  {status}  {req}")
        sys.exit(0)

if __name__ == "__main__":
    main()
