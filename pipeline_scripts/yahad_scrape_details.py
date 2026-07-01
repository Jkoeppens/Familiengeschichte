#!/usr/bin/env python3
"""
Scraped Yahad-in Unum Detailseiten für alle Killing Sites.
Input:  yahad_killing_sites.csv (aus dem Map-Endpoint)
Output: yahad_details.csv (strukturierte Metadaten pro Village)
Cache:  yahad_cache/ (rohe HTML-Seiten, damit Abbruch + Fortsetzung möglich)
"""

import csv
import time
import re
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path
from bs4 import BeautifulSoup

BASE_URL = "http://www.yahadmap.org/?village="
CACHE_DIR = Path("yahad_cache")
INPUT_CSV = "yahad_killing_sites.csv"
OUTPUT_CSV = "yahad_details.csv"
RATE_LIMIT = 1.2  # Sekunden zwischen Requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Referer": "http://www.yahadmap.org/",
}

OUTPUT_FIELDS = [
    "village_id", "slug", "name", "country", "lat", "lng",
    "execution_title", "killing_sites_count",
    "kind_of_place", "memorials", "period_of_occupation",
    "number_of_victims", "other_metadata",
    "witness_interview", "historical_note", "holocaust_by_bullets",
    "portal_url",
]


def fetch_html(village_id: str) -> str:
    cache_file = CACHE_DIR / f"{village_id}.html"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")

    url = BASE_URL + village_id
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        print(f"  ERROR {village_id}: {e}", file=sys.stderr)
        return ""

    cache_file.write_text(html, encoding="utf-8")
    time.sleep(RATE_LIMIT)
    return html


def parse_village(html: str, village_id: str, base_row: dict) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    row = dict(base_row)

    texte = soup.find(id="village_texte")
    if not texte:
        return row

    # Titel
    h2 = texte.find("h2")
    row["execution_title"] = h2.get_text(strip=True) if h2 else ""

    # Anzahl Killing Sites
    nb = texte.find(class_="nb_sites")
    row["killing_sites_count"] = nb.get_text(strip=True) if nb else ""

    # Strukturierte Metadaten (dl > dt/dd Paare)
    dl = texte.find("dl")
    meta = {}
    if dl:
        keys = [dt.get_text(strip=True).rstrip(":") for dt in dl.find_all("dt")]
        vals = [dd.get_text(strip=True) for dd in dl.find_all("dd")]
        meta = dict(zip(keys, vals))

    row["kind_of_place"]         = meta.get("Kind of place before", "")
    row["memorials"]             = meta.get("Memorials", "")
    row["period_of_occupation"]  = meta.get("Period of occupation", "")
    row["number_of_victims"]     = meta.get("Number of victims", "")
    # Alle anderen dl-Felder als JSON-String
    known = {"Kind of place before", "Memorials", "Period of occupation", "Number of victims"}
    extra = {k: v for k, v in meta.items() if k not in known}
    row["other_metadata"] = str(extra) if extra else ""

    # h3-Abschnitte: Text nach jedem h3-Header sammeln
    def text_after_h3(heading: str) -> str:
        h3 = texte.find("h3", string=re.compile(heading, re.I))
        if not h3:
            return ""
        parts = []
        for sib in h3.next_siblings:
            if sib.name == "h3":
                break
            if hasattr(sib, "get_text"):
                t = sib.get_text(separator=" ", strip=True)
                if t:
                    parts.append(t)
        return " ".join(parts).strip()

    row["witness_interview"]   = text_after_h3("Witness interview")
    row["historical_note"]     = text_after_h3("Historical note")
    row["holocaust_by_bullets"] = text_after_h3("Holocaust by bullets")

    return row


def main():
    CACHE_DIR.mkdir(exist_ok=True)

    # Unique Villages aus CSV laden (erste Zeile pro ID)
    villages = {}
    with open(INPUT_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            vid = row.get("village_id", "")
            if vid and vid not in villages:
                villages[vid] = row

    total = len(villages)
    print(f"{total} unique villages zu scrapen")

    # Bereits fertig: aus Output-CSV lesen falls vorhanden
    done = set()
    if Path(OUTPUT_CSV).exists():
        with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                done.add(row["village_id"])
        print(f"{len(done)} bereits gecacht, {total - len(done)} verbleibend")

    # Output-CSV öffnen (append wenn schon vorhanden, sonst neu mit Header)
    mode = "a" if done else "w"
    with open(OUTPUT_CSV, mode, newline="", encoding="utf-8") as outf:
        writer = csv.DictWriter(outf, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        if not done:
            writer.writeheader()

        for i, (vid, base_row) in enumerate(sorted(villages.items(), key=lambda x: int(x[0]))):
            if vid in done:
                continue

            print(f"[{i+1}/{total}] Village {vid}: {base_row.get('name','?')} ({base_row.get('country','?')})")

            html = fetch_html(vid)
            if not html:
                continue

            result = parse_village(html, vid, base_row)
            writer.writerow(result)
            outf.flush()

    print(f"\nFertig: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
