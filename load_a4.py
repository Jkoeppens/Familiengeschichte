#!/usr/bin/env python3
"""
load_a4.py — A4.1: Kontextereignisse laden; A4.2: Einheiten automatisch verknüpfen

Quellen:
  operationen_wk2.json   → Battle / Encirclement / Siege / Retreat / Surrender
  verbrechen_kontext.json → Atrocity / MassExecution / GhettoOperation / Deportation
  kz_lager.geojson       → Atrocity (subtype: KZ)
"""

import json
import math
import re
import sqlite3
from datetime import date
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))
from db import insert_event, insert_participation, _get_conn, _expand_begin, _expand_end

TODAY        = date.today().isoformat()
BASE         = Path(__file__).parent
RADIUS_KM    = 150   # A4.2 räumlicher Suchradius

# ─── Bekannte Koppermann-Einheiten ────────────────────────────────────────────

KOPPERMANN_PERSON = "person_koppermann_hj_1917"

# Strings in koppermann_einheit → actor_id
_EINHEIT_RE = [
    (re.compile(r"N\.A\. ?20"),             "unit_na20"),
    (re.compile(r"20\. Inf\.Div\.\(mot\.\)"), "unit_20_inf_div_mot"),
    (re.compile(r"20\. Inf\.Div\."),         "unit_20_inf_div_mot"),
    (re.compile(r"I\.R\. ?90"),              "unit_pzgrenrgt90"),
    (re.compile(r"Pz\.Gren\.Rgt\. ?90"),    "unit_pzgrenrgt90"),
    (re.compile(r"20\. Pz\.Gren\.Div\."),   "unit_20_pz_gren_div"),
]

def _einheit_to_actors(s: str) -> list[str]:
    if not s:
        return []
    found = []
    for pat, aid in _EINHEIT_RE:
        if pat.search(s):
            found.append(aid)
    return list(dict.fromkeys(found))  # dedupliziert, Reihenfolge erhalten

# ─── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _slug(s: str) -> str:
    s = s.lower()
    for ch in "-. /()–—":
        s = s.replace(ch, "_")
    s = re.sub(r'[^a-z0-9_]', '', s)
    return re.sub(r'_+', '_', s).strip('_')

def _precision_from_date(s: str | None) -> str:
    if not s:
        return "month"
    parts = s.split("-")
    if len(parts) == 3:
        return "day"
    if len(parts) == 2:
        return "month"
    return "year"

def _time_span(von: str | None, bis: str | None) -> dict:
    prec = _precision_from_date(von)
    return {"begin": von, "end": bis, "precision": prec}

def _place(lat, lon, name: str, radius_km: int, precision: str = "region") -> dict:
    return {
        "name": name,
        "lat": lat,
        "lon": lon,
        "precision": precision,
        "radius_km": radius_km,
    }

def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl   = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def _actor_exists(actor_id: str) -> bool:
    with _get_conn() as conn:
        row = conn.execute("SELECT 1 FROM actors WHERE id=?", (actor_id,)).fetchone()
    return row is not None

def _participation(event_id, actor_id, relation, role, note=None, certainty_override=None):
    p = {
        "event_id": event_id,
        "actor_id": actor_id,
        "relation": relation,
        "role": role,
        "note": note,
        "certainty_override": certainty_override,
        "created_at": TODAY,
    }
    insert_participation(p)

# ─── Typ-Mapping ──────────────────────────────────────────────────────────────

def _op_event_type(op: dict) -> tuple[str, str | None]:
    """(event_type, subtype)"""
    name = (op.get("name") or "").lower()
    eid  = (op.get("id")   or "").lower()
    typ  = op.get("typ", "")
    if "kessel"       in name or "einschließ" in eid or "einschli" in name:
        return "Encirclement", None
    if "blockade"     in name or "belager"    in name:
        return "Siege", None
    if "rückzug"      in name or "rueckzug"   in eid:
        return "Retreat", None
    if "kapitulation" in name:
        return "Surrender", None
    if typ == "stellungskrieg":
        return "Battle", "Stellungskrieg"
    return "Battle", None

_KATEGORIE_TO_TYPE = {
    "ghetto":          "GhettoOperation",
    "massaker":        "MassExecution",
    "repressalie":     "Atrocity",
    "strukturell":     "Atrocity",
    "vernichtungslager": "Atrocity",
    "deportation":     "Deportation",
}

_KZ_TYP_MAP = {
    "KZ / Außenlager":   "Konzentrationslager",
    "KZ / Hauptlager":   "Konzentrationslager",
    "Frühes KZ":         "Konzentrationslager",
    "Jugendlager":       "Arbeitslager",
    "SS-Baubrigade":     "Arbeitslager",
    "Sterbelager":       "Sterbelager",
    "Vernichtungslager": "Vernichtungslager",
    "Durchgangslager":   "Durchgangslager",
    "Ghetto":            "Ghetto",
}

# ─── A4.1 — Operationen ───────────────────────────────────────────────────────

def load_operationen() -> tuple[int, int]:
    """Gibt (events_geladen, participations_geladen) zurück."""
    with open(BASE / "operationen_wk2.json", encoding="utf-8") as f:
        ops = json.load(f)["operationen"]

    ev_count = part_count = 0
    for op in ops:
        raw_id    = op["id"]
        event_id  = f"event_op_{_slug(raw_id)}"
        ev_type, subtype = _op_event_type(op)
        z         = op.get("zentroid") or {}
        lat, lon  = z.get("lat"), z.get("lon")

        event = {
            "id":         event_id,
            "type":       ev_type,
            "label":      op["name"],
            "subtype":    subtype,
            "time_span":  _time_span(op.get("datum_von"), op.get("datum_bis")),
            "place":      _place(lat, lon, op.get("ort", ""), 150) if lat else None,
            "description": op.get("beschreibung"),
            "source": {
                "type":         "sekundaer",
                "certainty":    3,
                "generated_by": "direkt",
                "note":         op.get("koppermann_detail"),
            },
            "created_at": TODAY,
        }
        insert_event(event)
        ev_count += 1

        # Explizite Koppermann-Verknüpfung
        k = op.get("koppermann", "nein")
        if k in ("ja", "nahe"):
            relation = "had_participant" if k == "ja" else "occurred_in_presence_of"
            # Person
            _participation(event_id, KOPPERMANN_PERSON, relation, "soldier",
                           note=f"Quelle: operationen_wk2 koppermann={k!r}")
            part_count += 1
            # Einheiten aus koppermann_einheit
            for actor_id in _einheit_to_actors(op.get("koppermann_einheit") or ""):
                if _actor_exists(actor_id):
                    _participation(event_id, actor_id, relation, "unit",
                                   note=f"koppermann_einheit: {op.get('koppermann_einheit')}")
                    part_count += 1

    return ev_count, part_count


# ─── A4.1 — Verbrechen ───────────────────────────────────────────────────────

def load_verbrechen() -> tuple[int, int]:
    with open(BASE / "verbrechen_kontext.json", encoding="utf-8") as f:
        vbs = json.load(f)["verbrechen"]

    ev_count = part_count = 0
    for vb in vbs:
        raw_id   = vb["id"]
        event_id = f"event_vb_{_slug(raw_id)}"
        kat      = vb.get("kategorie", "strukturell")
        ev_type  = _KATEGORIE_TO_TYPE.get(kat, "Atrocity")
        z        = vb.get("zentroid") or {}
        lat, lon = z.get("lat"), z.get("lon")

        # atrocity_details
        opfer_gruppe = vb.get("opfer_gruppe") or ""
        victim_groups = [g.strip() for g in re.split(r',|;', opfer_gruppe) if g.strip()]

        atrocity_details = {
            "victims_count": vb.get("opfer_zahl"),
            "victim_groups": victim_groups,
            "method":        None,
            "camp_type":     "Vernichtungslager" if kat == "vernichtungslager" else None,
        }

        # Täter in description
        taeter = vb.get("taeter") or ""
        beschr = vb.get("beschreibung") or ""
        description = f"Täter: {taeter}\n{beschr}".strip() if taeter else beschr or None

        event = {
            "id":               event_id,
            "type":             ev_type,
            "label":            vb["name"],
            "subtype":          "Vernichtungslager" if kat == "vernichtungslager" else None,
            "time_span":        _time_span(vb.get("datum_von"), vb.get("datum_bis")),
            "place":            _place(lat, lon, vb.get("ort", ""), 80) if lat else None,
            "description":      description,
            "atrocity_details": atrocity_details,
            "source": {
                "type":         "sekundaer",
                "certainty":    3,
                "generated_by": "direkt",
            },
            "created_at": TODAY,
        }
        insert_event(event)
        ev_count += 1

        # Koppermann-Nähe als Participation
        naehe = vb.get("naehe_koppermann", "")
        if naehe in ("direkt", "zeitgleich", "region"):
            relation = ("occurred_in_presence_of" if naehe in ("direkt", "zeitgleich")
                        else "was_influenced_by")
            _participation(event_id, KOPPERMANN_PERSON, relation, "soldier",
                           note=f"naehe_koppermann={naehe!r}",
                           certainty_override=2)
            part_count += 1
            for actor_id in ["unit_20_inf_div_mot", "unit_20_pz_gren_div", "unit_pzgrenrgt90"]:
                if _actor_exists(actor_id):
                    _participation(event_id, actor_id, relation, "unit",
                                   note=f"naehe_koppermann={naehe!r}",
                                   certainty_override=2)
                    part_count += 1

    return ev_count, part_count


# ─── A4.1 — KZ-Lager ─────────────────────────────────────────────────────────

def load_kz_lager() -> tuple[int, int]:
    with open(BASE / "kz_lager.geojson", encoding="utf-8") as f:
        geo = json.load(f)

    ev_count = part_count = 0
    for feat in geo["features"]:
        p    = feat["properties"]
        fid  = p.get("id", "")
        lat  = p.get("lat")
        lon  = p.get("lon")
        if lat is None or lon is None:
            # Aus Geometrie
            coords = (feat.get("geometry") or {}).get("coordinates")
            if coords and len(coords) >= 2:
                lon, lat = coords[0], coords[1]

        event_id = f"event_kz_{_slug(fid)}"
        kz_typ   = p.get("typ", "")
        camp_type = _KZ_TYP_MAP.get(kz_typ)

        atrocity_details = {
            "victims_count": str(p["peak_population"]) if p.get("peak_population") else None,
            "victim_groups": [p["haftlinge"]] if p.get("haftlinge") else [],
            "method":        None,
            "camp_type":     camp_type,
        }

        name_str = p.get("name", "")
        hauptlager = p.get("hauptlager")
        label = f"{name_str} ({hauptlager})" if hauptlager and hauptlager != name_str else name_str

        event = {
            "id":               event_id,
            "type":             "Atrocity",
            "label":            label,
            "subtype":          "KZ",
            "time_span":        _time_span(p.get("datum_eroeffnung"), p.get("datum_schliessung")),
            "place": {
                "name":      name_str,
                "lat":       lat,
                "lon":       lon,
                "precision": "lokalisiert",
                "radius_km": 5,
            } if lat is not None else None,
            "description":      p.get("quelle"),
            "atrocity_details": atrocity_details,
            "source": {
                "type":         "ushmm",
                "certainty":    3,
                "generated_by": "direkt",
            },
            "created_at": TODAY,
        }
        insert_event(event)
        ev_count += 1

    return ev_count, part_count


# ─── A4.2 — Automatische Einheits-Verlinkung ─────────────────────────────────

def link_units_to_event(event: dict, radius_km: float = RADIUS_KM) -> list[dict]:
    """
    Findet alle MilitaryUnit-Actors deren UnitJoining-Events
    zeitlich und räumlich mit dem gegebenen Event überlappen.
    Gibt Liste von Participation-Dicts zurück.
    """
    place = event.get("place") or {}
    ev_lat = place.get("lat")
    ev_lon = place.get("lon")
    if ev_lat is None or ev_lon is None:
        return []

    ts       = event.get("time_span") or {}
    z_begin  = _expand_begin(ts.get("begin"))
    z_end    = _expand_end(ts.get("end"))
    if not z_begin or not z_end:
        return []

    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT p.actor_id, e.lat, e.lon
            FROM events e
            JOIN participations p ON e.id = p.event_id
            WHERE e.type = 'UnitJoining'
              AND p.role = 'unit'
              AND e.lat IS NOT NULL AND e.lon IS NOT NULL
              AND e.time_begin <= ? AND e.time_end >= ?
            """,
            (z_end, z_begin),
        ).fetchall()

    results = []
    seen: set[str] = set()
    for row in rows:
        actor_id = row[0]
        if actor_id in seen:
            continue
        dist = _haversine(ev_lat, ev_lon, row[1], row[2])
        if dist <= radius_km:
            seen.add(actor_id)
            results.append({
                "event_id":          event["id"],
                "actor_id":          actor_id,
                "relation":          "occurred_in_presence_of",
                "role":              "unit",
                "certainty_override": 2,
                "note":              f"entity_linking: {dist:.0f} km vom Ereignisort",
                "created_at":        TODAY,
            })
    return results


def run_auto_linking() -> int:
    """Verknüpft Einheiten mit allen Battle- und Atrocity-Events. Gibt Anzahl Participations zurück."""
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT data FROM events
            WHERE type IN ('Battle','Encirclement','Siege','Retreat','Surrender',
                           'Atrocity','MassExecution','GhettoOperation','Deportation')
              AND lat IS NOT NULL AND lon IS NOT NULL
            """
        ).fetchall()

    count = 0
    for row in rows:
        ev = json.loads(row[0])

        # Bereits explizit verknüpfte Actors (z.B. aus A4.1 Koppermann-Links)
        with _get_conn() as conn:
            existing = {
                r[0] for r in conn.execute(
                    "SELECT actor_id FROM participations WHERE event_id=? AND relation='had_participant'",
                    (ev["id"],)
                ).fetchall()
            }

        participations = link_units_to_event(ev)
        for p in participations:
            # had_participant nicht durch schwächere occurred_in_presence_of überschreiben
            if p["actor_id"] in existing:
                continue
            insert_participation(p)
            count += 1

    return count


# ─── Hauptprogramm ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== A4.1 — Kontextereignisse laden ===")

    print("\n[1/3] Operationen …")
    op_ev, op_part = load_operationen()
    print(f"      {op_ev} Events, {op_part} Participations")

    print("[2/3] Verbrechen …")
    vb_ev, vb_part = load_verbrechen()
    print(f"      {vb_ev} Events, {vb_part} Participations")

    print("[3/3] KZ-Lager …")
    kz_ev, kz_part = load_kz_lager()
    print(f"      {kz_ev} Events, {kz_part} Participations")

    total_ev   = op_ev + vb_ev + kz_ev
    total_part = op_part + vb_part + kz_part
    print(f"\n  → {total_ev} Events gesamt geladen")
    print(f"  → {total_part} explizite Participations (Koppermann)")

    print("\n=== A4.2 — Automatische Beteiligungsverknüpfung ===")
    auto_count = run_auto_linking()
    print(f"  → {auto_count} neue Participations (entity_linking, certainty_override=2)")

    # Gesamtstatistik
    with _get_conn() as conn:
        n_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        n_parts  = conn.execute("SELECT COUNT(*) FROM participations").fetchone()[0]
        n_actors = conn.execute("SELECT COUNT(*) FROM actors").fetchone()[0]
    print(f"\n  DB-Stand: {n_actors} Actors | {n_events} Events | {n_parts} Participations")
