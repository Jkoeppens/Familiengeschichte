#!/usr/bin/env bash
# Vollauf: alle Tessin-Bände neu durch Pipeline (ohne LLM), dann DB laden + Checks
set -euo pipefail

LOG="/Users/jakobkoppermann/Coding/Familiengeschichte/overnight.log"
cd /Users/jakobkoppermann/Coding/Familiengeschichte

echo_ts() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

echo_ts "=== START run_overnight.sh ===" > "$LOG"

# Alte *_neu_* Dateien entfernen (veraltete Parallelläufe)
rm -f tessin_bd*_neu*.json

BANDS=(1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 "16-1" "16-2" 17)

# ── Schritt 1+2: PDF → JSON (PyMuPDF blocks) ────────────────────────────────
for bd in "${BANDS[@]}"; do
    PDF="Bd_${bd}_ocr.pdf"
    if [ ! -f "$PDF" ]; then
        echo_ts "  SKIP $PDF (nicht gefunden)"
        continue
    fi
    echo_ts "--- Bd. ${bd}: tessin_pipeline ---"
    python3 tessin_pipeline.py --input "$PDF" 2>&1 | tee -a "$LOG"
done

# ── Schritt 3: normalize (nur Regex, kein LLM) → finalize ───────────────────
for bd in "${BANDS[@]}"; do
    RAW="tessin_bd${bd}.json"
    if [ ! -f "$RAW" ]; then
        echo_ts "  SKIP $RAW (nicht gefunden)"
        continue
    fi
    echo_ts "--- Bd. ${bd}: normalize + finalize ---"
    python3 normalize_pipeline.py --input "$RAW" --only-regex 2>&1 | tee -a "$LOG"
    python3 normalize_pipeline.py --input "$RAW" --postprocess --finalize 2>&1 | tee -a "$LOG"
done

# ── Schritt 4: DB leeren + laden ─────────────────────────────────────────────
echo_ts "=== DB leeren ==="
python3 - <<'PYEOF' 2>&1 | tee -a "$LOG"
import sqlite3
conn = sqlite3.connect('familiengeschichte.db')
c = conn.cursor()
c.execute('DELETE FROM participations')
c.execute('DELETE FROM events')
c.execute('DELETE FROM actors')
conn.commit()
conn.close()
print('DB geleert')
PYEOF

echo_ts "=== load_all_tessin.py ==="
python3 load_all_tessin.py 2>&1 | tee -a "$LOG"

# ── Schritt 5: Checks ─────────────────────────────────────────────────────────
echo_ts "=== POST-CHECKS ==="
python3 - 2>&1 | tee -a "$LOG" <<'PYEOF'
import sys, json, sqlite3
sys.path.insert(0, '/Users/jakobkoppermann/Coding/Familiengeschichte')

conn = sqlite3.connect('familiengeschichte.db')
c = conn.cursor()

# Check 1: N.A.20 in JSON
from pathlib import Path
data = json.loads(Path('tessin_bd4_final.json').read_text())
na20 = [e for e in data if e.get('einheit','') == 'Nachrichten-Abt. 20']
print(f"\n[CHECK 1] N.A.20 in tessin_bd4_final.json: {len(na20)} Treffer")
for e in na20:
    print(f"  einheit={e.get('einheit')!r}  nummer={e.get('nummer')!r}  wehrkreis={e.get('wehrkreis')!r}  heimatgarnison={e.get('heimatgarnison')!r}")

# Check 2: Actor + parent_unit_id in DB
row = c.execute("SELECT pref_label, data FROM actors WHERE id='unit_20_nachrichten_abt_20'").fetchone()
if row:
    d = json.loads(row[1])
    print(f"\n[CHECK 2] unit_20_nachrichten_abt_20:")
    print(f"  parent_unit_id: {d.get('parent_unit_id')!r}")
    print(f"  wehrkreis     : {d.get('wehrkreis')!r}")
    print(f"  heimatgarnison: {d.get('heimatgarnison')!r}")
    ok = d.get('parent_unit_id') == 'unit_20_pz_gren_div'
    print(f"  → {'OK' if ok else 'FAIL'}: parent_unit_id={'unit_20_pz_gren_div' if ok else '?'}")
else:
    print("\n[CHECK 2] FAIL: unit_20_nachrichten_abt_20 nicht in DB")

# Check 3: unit_20_pz_gren_div UnitJoining-Events
row2 = c.execute("SELECT pref_label FROM actors WHERE id='unit_20_pz_gren_div'").fetchone()
if row2:
    joins = c.execute("""
        SELECT COUNT(*) FROM participations p
        JOIN events e ON p.event_id = e.id
        WHERE p.actor_id = 'unit_20_pz_gren_div'
          AND json_extract(e.data, '$.type') = 'UnitJoining'
    """).fetchone()[0]
    print(f"\n[CHECK 3] unit_20_pz_gren_div:")
    print(f"  pref_label         : {row2[0]!r}")
    print(f"  UnitJoining-Events : {joins}")
else:
    print("\n[CHECK 3] unit_20_pz_gren_div nicht in DB")

# Check 4: DB-Gesamtzahlen
total_actors = c.execute('SELECT COUNT(*) FROM actors').fetchone()[0]
total_events = c.execute('SELECT COUNT(*) FROM events').fetchone()[0]
total_parts  = c.execute('SELECT COUNT(*) FROM participations').fetchone()[0]
joins_total  = c.execute("SELECT COUNT(*) FROM events WHERE json_extract(data,'$.type')='UnitJoining'").fetchone()[0]
print(f"\n[CHECK 4] DB-Gesamt:")
print(f"  Actors:      {total_actors}")
print(f"  Events:      {total_events}  (davon UnitJoining: {joins_total})")
print(f"  Participat.: {total_parts}")

conn.close()
PYEOF

echo_ts "=== FERTIG ==="
