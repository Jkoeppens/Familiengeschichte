#!/usr/bin/env python3
"""
normalize_with_llm.py — OCR-normalisierung und GeoNames-Nachschlag für ungelöste Ortsnamen

1. Liest nicht_aufgeloest.json
2. Klassifiziert: OCR-Artefakt / Org-Kürzel → Blacklist | Ort-Kandidat → Ollama
3. Ollama (llama3.1:8b) normalisiert den Ortsnamen
4. GeoNames schlägt den normalisierten Namen nach
5. Aktualisiert DB + gazeteer_cache.json
"""

import json
import os
import re
import sqlite3
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path

DB_PATH    = Path(__file__).parent / "familiengeschichte.db"
CACHE_FILE = Path(__file__).parent / "gazeteer_cache.json"
UNRESOLVED = Path(__file__).parent / "nicht_aufgeloest.json"
INVENTAR   = Path(__file__).parent / "gazeteer_inventar.json"

GEONAMES_USER = os.environ.get("GEONAMES_USER", "")
OLLAMA_MODEL  = "llama3.1:8b"

VOWELS = set('aeiouäöüAEIOUÄÖÜ')


# ─── Klassifikation ───────────────────────────────────────────────────────────

def classify(name: str) -> str:
    if re.match(r'^[\d\s\W]+$', name):
        return "ocr_artefakt"
    if re.search(r'\d{4,}', name):
        return "ocr_artefakt"
    if re.match(r'^[A-ZÄÖÜ0-9]{2,8}[\.\-\(\)]?$', name):
        return "org_kuerzel"
    org_patterns = [
        r'^(Hgr|AOK|OKH|OKW|BdE|WK|Befh|Armeeabt|Kampfgr)',
        r'(Auffr\.|Aufst\.|z\.Vfg|Reserve|Ersatz)',
        r'^\(.*\)$',
        r'^[,\.\(\)\"\'\*\-–—/\\]+',
    ]
    for p in org_patterns:
        if re.search(p, name):
            return "org_kuerzel"
    if len(name) <= 3:
        return "org_kuerzel"
    if len(name) >= 4 and not any(c in VOWELS for c in name):
        return "org_kuerzel"
    return "ort_kandidat"


# ─── Ollama ───────────────────────────────────────────────────────────────────

def ollama_normalize(name: str) -> str | None:
    prompt = (
        "Dies ist ein Ortsname aus deutschen Militärakten des Zweiten Weltkriegs, "
        "möglicherweise mit OCR-Fehler oder veralteter Schreibweise. "
        "Gib den korrekten modernen Ortsnamen auf Englisch oder Deutsch zurück, "
        "oder 'unbekannt' wenn es kein echter Ortsname ist (z.B. Abkürzung, Truppenbezeichnung). "
        "Antworte NUR mit dem Ortsnamen oder 'unbekannt', kein weiterer Text.\n"
        f"OCR-Name: {name}"
    )
    try:
        result = subprocess.run(
            ["ollama", "run", OLLAMA_MODEL, prompt],
            capture_output=True, text=True, timeout=30, encoding="utf-8"
        )
        out = result.stdout.strip()
        # Nur erste Zeile, Anführungszeichen entfernen
        out = out.split('\n')[0].strip().strip('"\'')
        if not out or out.lower() in ("unbekannt", "unknown", "keine", "none", "-", "n/a"):
            return None
        return out
    except Exception:
        return None


# ─── GeoNames ────────────────────────────────────────────────────────────────

def geonames_lookup(name: str) -> dict | None:
    if not GEONAMES_USER:
        return None
    params = urllib.parse.urlencode({
        "q": name, "maxRows": 1, "username": GEONAMES_USER,
        "type": "json",
    })
    url = f"http://api.geonames.org/searchJSON?{params}"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        hits = data.get("geonames", [])
        if hits:
            h = hits[0]
            return {"lat": float(h["lat"]), "lon": float(h["lng"]),
                    "precision": "stadt", "radius_km": 20, "source": "geonames_llm"}
    except Exception:
        pass
    return None


# ─── Hauptprogramm ────────────────────────────────────────────────────────────

def main() -> None:
    with open(UNRESOLVED, encoding="utf-8") as f:
        unresolved = json.load(f)
    with open(INVENTAR, encoding="utf-8") as f:
        freq = {v["name"]: v["count"] for v in json.load(f)}
    cache: dict[str, dict] = {}
    if CACHE_FILE.exists():
        with open(CACHE_FILE, encoding="utf-8") as f:
            cache = json.load(f)

    # Klassifizieren
    cats: dict[str, list] = {"ocr_artefakt": [], "org_kuerzel": [], "ort_kandidat": []}
    for name in unresolved:
        cats[classify(name)].append(name)

    # Org-Kürzel → Blacklist im Cache
    bl_added = 0
    for name in cats["ocr_artefakt"] + cats["org_kuerzel"]:
        key = name.lower()
        if key not in cache:
            cache[key] = {"precision": "schauplatz", "source": "blacklist_llm"}
            bl_added += 1

    print(f"Klassifikation:")
    print(f"  ocr_artefakt:  {len(cats['ocr_artefakt'])} → Blacklist")
    print(f"  org_kuerzel:   {len(cats['org_kuerzel'])} → Blacklist")
    print(f"  ort_kandidat:  {len(cats['ort_kandidat'])} → Ollama + GeoNames")
    print(f"  Blacklist-Einträge neu: {bl_added}")

    # Ort-Kandidaten sortiert nach Häufigkeit
    candidates = sorted(cats["ort_kandidat"], key=lambda n: -freq.get(n, 0))

    llm_normalized = 0
    llm_unknown    = 0
    geonames_found = 0
    still_open: list[str] = []

    print(f"\nNormalisiere {len(candidates)} Ort-Kandidaten mit {OLLAMA_MODEL}...")
    for i, name in enumerate(candidates):
        orig_key = name.lower()
        if orig_key in cache:
            continue  # bereits im Cache

        if (i + 1) % 20 == 0:
            print(f"  [{i+1}/{len(candidates)}] ...", flush=True)

        normalized = ollama_normalize(name)

        if normalized is None or normalized.lower() == name.lower():
            # LLM weiß es nicht / keine Verbesserung
            llm_unknown += 1
            # Trotzdem GeoNames mit Originalname versuchen
            geo = geonames_lookup(name)
            if geo:
                cache[orig_key] = geo
                geonames_found += 1
            else:
                still_open.append(name)
            continue

        llm_normalized += 1
        norm_key = normalized.lower()

        # Wenn normalisierter Name bereits im Cache
        if norm_key in cache and cache[norm_key].get("precision") != "schauplatz":
            cache[orig_key] = {**cache[norm_key], "source": cache[norm_key]["source"] + "_via_llm"}
            geonames_found += 1
            continue

        # GeoNames mit normalisiertem Namen
        geo = geonames_lookup(normalized)
        if geo:
            cache[norm_key] = geo
            cache[orig_key] = {**geo, "source": "geonames_llm"}
            geonames_found += 1
        else:
            # GeoNames mit Originalname als Fallback
            geo2 = geonames_lookup(name)
            if geo2:
                cache[orig_key] = {**geo2, "source": "geonames_llm_fallback"}
                geonames_found += 1
            else:
                still_open.append(name)

    print(f"\nOllama-Ergebnis:")
    print(f"  normalisiert:  {llm_normalized}")
    print(f"  unbekannt:     {llm_unknown}")
    print(f"  via GeoNames aufgelöst: {geonames_found}")
    print(f"  weiterhin offen:        {len(still_open)}")

    # Cache speichern
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    # DB aktualisieren: Events mit nunmehr aufgelösten Namen
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, data FROM events WHERE type='UnitJoining' AND lat IS NULL"
    ).fetchall()

    updated = 0
    for row in rows:
        ev = json.loads(row["data"])
        place = ev.get("place") or {}
        ort_name = place.get("name") or ""
        if not ort_name:
            continue
        result = cache.get(ort_name.lower())
        if not result:
            continue
        if result.get("precision") == "schauplatz":
            continue
        if "lat" not in result:
            continue

        place["lat"]       = result["lat"]
        place["lon"]       = result["lon"]
        place["precision"] = result["precision"]
        place["radius_km"] = result.get("radius_km", 20)
        ev["place"] = place
        conn.execute(
            "UPDATE events SET lat=?, lon=?, data=? WHERE id=?",
            (result["lat"], result["lon"],
             json.dumps(ev, ensure_ascii=False), row["id"]),
        )
        updated += 1

    conn.commit()
    conn.close()

    # nicht_aufgeloest aktualisieren
    with open(UNRESOLVED, "w", encoding="utf-8") as f:
        json.dump(sorted(still_open), f, ensure_ascii=False, indent=2)

    # Gesamtstatistik
    total_uj = sqlite3.connect(DB_PATH).execute(
        "SELECT COUNT(*) FROM events WHERE type='UnitJoining'"
    ).fetchone()[0]
    with_coords = sqlite3.connect(DB_PATH).execute(
        "SELECT COUNT(*) FROM events WHERE type='UnitJoining' AND lat IS NOT NULL"
    ).fetchone()[0]

    print(f"\n── Neue Gesamtabdeckung ────────────────────────────────")
    print(f"  Events aktualisiert (diese Runde): {updated}")
    print(f"  UnitJoining mit Koordinaten:  {with_coords} / {total_uj}  ({with_coords/total_uj*100:.1f} %)")
    print(f"  nicht_aufgeloest.json: {len(still_open)} einzigartige Namen")


if __name__ == "__main__":
    main()
