#!/usr/bin/env python3
"""Lädt Koppermann-Referenzinstanz in familiengeschichte.db und testet verorte/kontext."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db

BASE = Path(__file__).parent

# ─── DB leeren und neu befüllen ────────────────────────────────────────────────

with db._get_conn() as conn:
    conn.execute("DELETE FROM participations")
    conn.execute("DELETE FROM events")
    conn.execute("DELETE FROM actors")

actors        = json.loads((BASE / "actors.json").read_text(encoding="utf-8"))
events        = json.loads((BASE / "events.json").read_text(encoding="utf-8"))
participations = json.loads((BASE / "participations.json").read_text(encoding="utf-8"))

for a in actors:
    db.insert_actor(a)
for e in events:
    db.insert_event(e)
for p in participations:
    db.insert_participation(p)

print(f"Geladen: {len(actors)} actors | {len(events)} events | {len(participations)} participations\n")

# ─── Hilfsfunktion ─────────────────────────────────────────────────────────────

def fmt(results: list[dict]) -> None:
    if not results:
        print("  (keine Ergebnisse)")
        return
    for r in results:
        place  = r.get("place") or {}
        src    = r.get("source") or {}
        part   = r.get("_participation") or {}
        print(f"  event_id   : {r['id']}")
        print(f"  type       : {r['type']}")
        print(f"  ort        : {place.get('name')} ({place.get('modern_name')})")
        print(f"  lat/lon    : {place.get('lat')} / {place.get('lon')}")
        print(f"  certainty  : {src.get('certainty')}  source_type={src.get('type')}  generated_by={src.get('generated_by')}")
        print(f"  relation   : {part.get('relation')}  role={part.get('role')}")
        print()

# ─── Test 1: verorte 1943-08-28 → Gorki, certainty=5, source.type=wast ────────

print("═" * 60)
print("verorte('person_koppermann_hj_1917', '1943-08-28')")
print("Erwartung: Gorki, lat=54.02, lon=27.1, certainty=5, source.type=wast")
print("─" * 60)
fmt(db.verorte("person_koppermann_hj_1917", "1943-08-28"))

# ─── Test 2: verorte 1943-11 → Trier, certainty=5, source.type=wast ───────────

print("═" * 60)
print("verorte('person_koppermann_hj_1917', '1943-11')")
print("Erwartung: Trier, lat=49.75, lon=6.64, certainty=5, source.type=wast")
print("─" * 60)
fmt(db.verorte("person_koppermann_hj_1917", "1943-11"))

# ─── Test 3: verorte 1941-07 → Minsk-Raum, certainty=2, entity_linking ────────

print("═" * 60)
print("verorte('person_koppermann_hj_1917', '1941-07')")
print("Erwartung: Minsk-Raum, certainty=2, generated_by=entity_linking")
print("─" * 60)
fmt(db.verorte("person_koppermann_hj_1917", "1941-07"))

# ─── Test 4: kontext 1941-07 → enthält event_minsk_ghetto_1941 ────────────────

print("═" * 60)
print("kontext('person_koppermann_hj_1917', '1941-07', radius_km=200)")
print("Erwartung: enthält event_minsk_ghetto_1941, relation=occurred_in_presence_of")
print("─" * 60)
results = db.kontext("person_koppermann_hj_1917", "1941-07", radius_km=200)
fmt(results)
ids = [r["id"] for r in results]
if "event_minsk_ghetto_1941" in ids:
    print("  ✓  event_minsk_ghetto_1941 gefunden")
else:
    print("  ✗  event_minsk_ghetto_1941 NICHT gefunden")
    sys.exit(1)

print("\n✓  Alle Tests bestanden.")
