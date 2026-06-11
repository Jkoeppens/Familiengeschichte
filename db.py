#!/usr/bin/env python3
"""
db.py — Datenbankzugriff für Familiengeschichte-Datenbank (SQLite)
"""

import sqlite3
import json
import math
import calendar
from pathlib import Path
from typing import Optional

try:
    import jsonschema
except ImportError:
    raise ImportError("jsonschema nicht installiert: pip install jsonschema")

DB_PATH = Path(__file__).parent / "familiengeschichte.db"
SCHEMA_DIR = Path(__file__).parent / "schema"

# ─── DDL ──────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS actors (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL,
    pref_label  TEXT NOT NULL,
    data        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id             TEXT PRIMARY KEY,
    type           TEXT NOT NULL,
    time_begin     TEXT,
    time_end       TEXT,
    time_precision TEXT,
    lat            REAL,
    lon            REAL,
    data           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_time   ON events (time_begin, time_end);
CREATE INDEX IF NOT EXISTS idx_events_latlon ON events (lat, lon);

CREATE TABLE IF NOT EXISTS participations (
    event_id  TEXT NOT NULL,
    actor_id  TEXT NOT NULL,
    relation  TEXT NOT NULL,
    role      TEXT NOT NULL,
    data      TEXT NOT NULL,
    PRIMARY KEY (event_id, actor_id, role)
);

CREATE INDEX IF NOT EXISTS idx_participations_actor ON participations (actor_id);
"""


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _get_conn() as conn:
        conn.executescript(_DDL)


# ─── Schema-Validierung ───────────────────────────────────────────────────────

_schema_cache: dict[str, dict] = {}


def _load_schema(name: str) -> dict:
    if name not in _schema_cache:
        with open(SCHEMA_DIR / f"{name}.schema.json", encoding="utf-8") as f:
            _schema_cache[name] = json.load(f)
    return _schema_cache[name]


def _validate(data: dict, schema_name: str) -> None:
    jsonschema.validate(data, _load_schema(schema_name), cls=jsonschema.Draft7Validator)


# ─── Datumsnormalisierung ─────────────────────────────────────────────────────

def _expand_begin(s: Optional[str]) -> Optional[str]:
    """YYYY → YYYY-01-01, YYYY-MM → YYYY-MM-01."""
    if s is None:
        return None
    parts = s.split("-")
    if len(parts) == 1:
        return f"{s}-01-01"
    if len(parts) == 2:
        return f"{s}-01"
    return s


def _expand_end(s: Optional[str]) -> Optional[str]:
    """YYYY → YYYY-12-31, YYYY-MM → YYYY-MM-{last day}."""
    if s is None:
        return None
    parts = s.split("-")
    if len(parts) == 1:
        return f"{s}-12-31"
    if len(parts) == 2:
        y, m = int(parts[0]), int(parts[1])
        return f"{s}-{calendar.monthrange(y, m)[1]:02d}"
    return s


def _zeitpunkt_range(zeitpunkt: str) -> tuple[str, str]:
    return _expand_begin(zeitpunkt), _expand_end(zeitpunkt)


# ─── Einfügeoperationen ───────────────────────────────────────────────────────

def insert_actor(actor: dict) -> None:
    _validate(actor, "actor")
    with _get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO actors (id, type, pref_label, data) VALUES (?, ?, ?, ?)",
            (actor["id"], actor["type"], actor["pref_label"],
             json.dumps(actor, ensure_ascii=False)),
        )


def insert_event(event: dict) -> None:
    _validate(event, "event")
    ts = event["time_span"]
    place = event.get("place") or {}
    with _get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO events
               (id, type, time_begin, time_end, time_precision, lat, lon, data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event["id"], event["type"],
                _expand_begin(ts.get("begin")),
                _expand_end(ts.get("end")),
                ts.get("precision"),
                place.get("lat"), place.get("lon"),
                json.dumps(event, ensure_ascii=False),
            ),
        )


def insert_participation(participation: dict) -> None:
    _validate(participation, "participation")
    with _get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO participations
               (event_id, actor_id, relation, role, data)
               VALUES (?, ?, ?, ?, ?)""",
            (
                participation["event_id"], participation["actor_id"],
                participation["relation"], participation["role"],
                json.dumps(participation, ensure_ascii=False),
            ),
        )


# ─── Abfrageoperationen ───────────────────────────────────────────────────────

def verorte(actor_id: str, zeitpunkt: str) -> list[dict]:
    """Alle Events des Akteurs, die zeitpunkt enthalten, nach certainty absteigend."""
    z_begin, z_end = _zeitpunkt_range(zeitpunkt)
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT e.data, p.data AS pdata
            FROM events e
            JOIN participations p ON e.id = p.event_id
            WHERE p.actor_id = ?
              AND (e.time_begin IS NULL OR e.time_begin <= ?)
              AND (e.time_end   IS NULL OR e.time_end   >= ?)
            ORDER BY json_extract(e.data, '$.source.certainty') DESC
            """,
            (actor_id, z_end, z_begin),
        ).fetchall()
    return [
        {**json.loads(r["data"]), "_participation": json.loads(r["pdata"])}
        for r in rows
    ]


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Entfernung in km (Haversine)."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


_UNIT_TYPE_RANK = {
    'Kompanie': 1, 'Bataillon': 2, 'Abteilung': 2,
    'Regiment': 3, 'Division': 4, 'Korps': 5,
    'Armee': 6, 'Heeresgruppe': 7, 'Unknown': 0, 'Sonderverband': 0,
}


def get_hierarchy(unit_id: str) -> list[str]:
    """Gibt Kette [unit_id, parent_id, grandparent_id, ...] zurück.
    Traversiert parent_unit_id; Fallback auf UnitJoining-subordinate-Events.
    Stoppt bei Armee/Heeresgruppe oder wenn keine übergeordnete Einheit gefunden.
    Validiert: Eltern müssen höheren Rang als Kind haben."""
    STOP_TYPES = {'Armee', 'Heeresgruppe'}
    chain: list[str] = []
    current = unit_id
    visited: set[str] = set()
    current_rank = 0

    while current and current not in visited:
        visited.add(current)
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT data FROM actors WHERE id = ?", (current,)
            ).fetchone()
        if not row:
            break
        actor_data = json.loads(row["data"])
        unit_type = actor_data.get("unit_type", "Unknown")
        rank = _UNIT_TYPE_RANK.get(unit_type, 0)

        # Eltern müssen höheren Rang haben (oder akzeptierter erster Schritt)
        if chain and rank <= current_rank and rank != 0:
            break
        if rank == 0 and chain:
            break  # Unknown-Typ als Eltern stoppen die Kette

        chain.append(current)
        current_rank = max(current_rank, rank)

        if unit_type in STOP_TYPES:
            break

        # 1. parent_unit_id direkt auf Actor
        parent_id = actor_data.get("parent_unit_id")

        # 2. Fallback: UnitJoining-Event wo diese Unit subordinate ist
        if not parent_id:
            with _get_conn() as conn:
                r2 = conn.execute(
                    """
                    SELECT p2.actor_id
                    FROM events e
                    JOIN participations p1
                         ON e.id = p1.event_id
                        AND p1.actor_id = ?
                        AND p1.role = 'subordinate'
                    JOIN participations p2
                         ON e.id = p2.event_id
                        AND p2.role = 'superior'
                    WHERE e.type = 'UnitJoining'
                      AND json_extract(e.data, '$.subtype') = 'Unterstellung'
                    LIMIT 1
                    """,
                    (current,),
                ).fetchone()
            if r2:
                parent_id = r2[0]

        current = parent_id

    return chain


def kontext(actor_id: str, zeitpunkt: str, radius_km: float = 50.0) -> list[dict]:
    """Events in radius_km um den Standort des Akteurs zu zeitpunkt."""
    actor_events = verorte(actor_id, zeitpunkt)
    actor_lat, actor_lon = None, None
    # UnitJoining-Events zuerst: repräsentiert den Tessin-Standort (direkte Quelle).
    # Verhindert, dass lang laufende Kontext-Events (z.B. Ghetto 1941–1943) die
    # Positionsbestimmung dominieren, wenn das Gerät längst woanders war.
    for preferred_type in ("UnitJoining", None):
        for ev in actor_events:
            if preferred_type is not None and ev.get("type") != preferred_type:
                continue
            place = ev.get("place") or {}
            if place.get("lat") is not None and place.get("lon") is not None:
                actor_lat, actor_lon = place["lat"], place["lon"]
                break
        if actor_lat is not None:
            break

    if actor_lat is None:
        return []

    z_begin, z_end = _zeitpunkt_range(zeitpunkt)
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT e.data, e.lat, e.lon, p.data AS pdata
            FROM events e
            JOIN participations p ON e.id = p.event_id
            WHERE e.lat IS NOT NULL AND e.lon IS NOT NULL
              AND (e.time_begin IS NULL OR e.time_begin <= ?)
              AND (e.time_end   IS NULL OR e.time_end   >= ?)
            """,
            (z_end, z_begin),
        ).fetchall()

    seen: set[str] = set()
    results = []
    for row in rows:
        if _haversine(actor_lat, actor_lon, row["lat"], row["lon"]) <= radius_km:
            ev = json.loads(row["data"])
            if ev["id"] not in seen:
                seen.add(ev["id"])
                results.append({**ev, "_participation": json.loads(row["pdata"])})
    return results


# ─── Init ─────────────────────────────────────────────────────────────────────

init_db()

if __name__ == "__main__":
    print(f"DB:      {DB_PATH}")
    print(f"Schemas: {[s.name for s in sorted(SCHEMA_DIR.glob('*.schema.json'))]}")
    with _get_conn() as conn:
        for table in ("actors", "events", "participations"):
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table}: {n} Einträge")
