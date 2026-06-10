"""
Tessin Bd. 4 PDF → JSON pipeline.
Extracts all unit entries from Bd_4_ocr.pdf and outputs tessin_bd4.json.

Steps:
  1. Extract text page-by-page, strip running headers
  2. Detect unit-entry boundaries → chunks_debug.json
  3. Parse each chunk → structured record
  4. QC + output → tessin_bd4.json
"""

import pdfplumber
import json
import re
from pathlib import Path

PDF_PATH = Path('Bd_4_ocr.pdf')
DEBUG_PATH = Path('chunks_debug.json')
OUTPUT_PATH = Path('tessin_bd4.json')

# ── 1. text extraction ────────────────────────────────────────────────────────

SECTION_HEADINGS = {
    'Kommandobehörden', 'Infanterie', 'SchnelleTruppen', 'Artillerie',
    'Pioniere', 'Nachrichtentruppen', 'Versorgungstruppen', 'Kraftfahrtruppen',
    'Sanitätstruppen', 'Veterinärtruppen', 'Feldjäger', 'Kriegsgefangene',
    'Sicherungstruppen', 'Landesschützen', 'Luftwaffe', 'WaffenSS',
    'Verbündete', 'Sonstiges',
}

def is_running_header(line: str) -> bool:
    """First 1-2 lines of a page are running headers like '20 Infanterie' or 'Infanterie 20'."""
    stripped = line.strip()
    if not stripped:
        return False
    tokens = stripped.split()
    if len(tokens) > 4:
        return False
    has_num = any(t.isdigit() or re.fullmatch(r'\d+', t) for t in tokens)
    has_word = any(t in SECTION_HEADINGS or re.search(r'[A-ZÄÖÜ][a-zäöü]{3,}', t) for t in tokens)
    # Also strip lone page numbers
    if len(tokens) == 1 and tokens[0].isdigit():
        return True
    return has_num and has_word and len(stripped) < 60


def extract_pages(pdf_path: Path) -> list[str]:
    """Return list of cleaned page texts with running headers removed."""
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ''
            lines = text.splitlines()
            # Strip up to 2 leading running-header lines
            start = 0
            for j in range(min(2, len(lines))):
                if is_running_header(lines[j]):
                    start = j + 1
            pages.append('\n'.join(lines[start:]))
    return pages


# ── 2. chunk detection ────────────────────────────────────────────────────────

# Matches a formation-date after *: "* 26.8.1939", "* Nov. 1944", "* Herbst 1943"
RE_STAR_DATE = re.compile(
    r'\*\s*('
    r'\d{1,2}[\.,]\d{1,2}[\.,]\d{4}|'   # 1.11.1940
    r'\d{1,2}[\.,]\s*\d{4}|'             # 1.1940
    r'[A-Z][a-z]{2,}\.?\s*\d{4}|'       # Nov. 1944
    r'[A-Z][a-z]{4,}\.?\s*19\d{2}|'     # Herbst 1943
    r'\d{4}\s'                            # 1939 ...
    r')'
)

# Fallback for major divisions that have (WK...) but OCR dropped the *
RE_WK_HEADER = re.compile(r'\(WK\s+[IVX]', re.IGNORECASE)

# Section/chapter lines to skip when looking backwards for a unit name
RE_SECTION = re.compile(
    r'^[A-Z]\.\s*(Infanterie|Schnell|Artillerie|Pionier|Nachrichten|Versorgungs|'
    r'Kraftfahr|Sanität|Feldjäger|Sicherungs|Luftwaffe|Waffen|Verbündete)',
    re.IGNORECASE,
)


def _line_offsets(lines: list[str]) -> list[int]:
    """Character offset of the start of each line in the joined text."""
    offs = [0]
    for ln in lines:
        offs.append(offs[-1] + len(ln) + 1)
    return offs


def find_chunks(full_text: str) -> list[dict]:
    """Star-centric chunk detection.

    Primary signal: every Tessin entry has a '*<date>' formation marker.
    For each such marker we walk back to find where the entry name is, then
    record that position as a chunk start.

    Fallback: major divisions that have (WK...) but whose * was dropped by OCR.
    """
    lines = full_text.splitlines()
    loff = _line_offsets(lines)   # loff[i] = char offset of lines[i]

    def is_skip_line(ln: str) -> bool:
        """Lines that are not unit names: (WK...), section headings, blank."""
        s = ln.strip()
        return (not s
                or s.startswith('(')
                or RE_SECTION.match(s)
                or re.match(r'^[A-Z]\.\s+\w', s))   # "A. Kommandobehörden"

    chunk_starts: set[int] = set()   # set of char offsets

    # ── primary pass: star-date lines ────────────────────────────────────────
    for i, line in enumerate(lines):
        if not RE_STAR_DATE.search(line):
            continue
        stripped = line.strip()

        # Inline case: "UnitName * date…" — * is NOT the first non-space char
        if not stripped.startswith('*'):
            star_pos = line.find('*')
            before = line[:star_pos].strip()
            if before:
                chunk_starts.add(loff[i])
                continue

        # Line-start case: "* date…" — name is on a preceding line
        for back in range(1, 5):
            if i - back < 0:
                break
            candidate = lines[i - back]
            if is_skip_line(candidate):
                continue
            # Skip lines that are already inside a chunk body (indented continuation)
            if candidate.startswith('  ') or candidate.startswith('\t'):
                continue
            chunk_starts.add(loff[i - back])
            break

    # ── fallback pass: (WK...) headers without * ────────────────────────────
    for i, line in enumerate(lines):
        if not RE_WK_HEADER.search(line):
            continue
        # The unit name is the preceding non-skip line
        for back in range(1, 4):
            if i - back < 0:
                break
            candidate = lines[i - back]
            if is_skip_line(candidate):
                continue
            chunk_starts.add(loff[i - back])
            break

    sorted_starts = sorted(chunk_starts)

    # ── build raw chunks ─────────────────────────────────────────────────────
    chunks = []
    for idx, start in enumerate(sorted_starts):
        end = sorted_starts[idx + 1] if idx + 1 < len(sorted_starts) else len(full_text)
        raw = full_text[start:end].strip()
        if raw:
            chunks.append({'offset': start, 'raw': raw})
    return chunks


# ── 3. structured parsing ─────────────────────────────────────────────────────

RE_HEADER = re.compile(
    rf'^(\d{{1,3}})\.\s*(.+?)(?:\s*\(WK\s+([IVX]+(?:\s*\d+)?(?:.*?))?\))?$',
    re.MULTILINE,
)
RE_WK_LINE = re.compile(r'\(WK\s+([IVX]+(?:\s*/\s*[IVX]+)?)\s*(?:,?\s*E\s*([\w\s\-/]+))?\)')
RE_AUFGESTELLT = re.compile(r'\*\s*(.+?)(?=\n[A-Z]|\nG:|\nU:|\nE:|\nUnterstellung|\Z)', re.DOTALL)

# Unterstellung table line:  year  months  korps  armee  hgr  theater  ort
RE_USTERZ_YEAR = re.compile(r'^(\d{4})\s')
RE_USTERZ_ROW = re.compile(
    r'^(\d{4})?\s+'               # optional year
    r'(\w+(?:\./\w+)?)\s+'        # month(s), e.g. "Jan." or "Jan./Febr."
    r'(.+)$'                      # rest of line
)

RE_G = re.compile(r'\bG:\s*(.+?)(?=\nU:|\nE:|\nUnterstellung|\Z)', re.DOTALL)
RE_U = re.compile(r'\bU:\s*(.+?)(?=\nG:|\nE:|\nUnterstellung|\Z)', re.DOTALL)
RE_E = re.compile(r'\bE:\s*(.+?)(?=\nG:|\nU:|\nUnterstellung|\Z)', re.DOTALL)

RE_USTERZ_BLOCK = re.compile(
    r'Unterstellung\s*:\s*\n(.*?)(?=\n[A-Z][a-z]+ersatz|\nFeldersatz|\Z)',
    re.DOTALL,
)


def parse_unterstellung_table(block: str) -> list[dict]:
    rows = []
    current_year = None
    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        # Year continuation
        m_year = RE_USTERZ_YEAR.match(line)
        if m_year:
            current_year = int(m_year.group(1))

        # Try to parse a month-row
        # Format: [YYYY] MONTH[/MONTH]  KORPS  ARMEE  [HGR]  [THEATER]  [ORT]
        tokens = line.split()
        if not tokens:
            continue

        tidx = 0
        year = current_year
        if tokens[0].isdigit() and len(tokens[0]) == 4:
            year = int(tokens[0])
            current_year = year
            tidx = 1

        if tidx >= len(tokens):
            continue

        # Month token: starts with a German month abbreviation
        month_tok = tokens[tidx]
        if not re.match(r'^(Jan|Febr?|Mär|Apr|Mai|Juni?|Juli?|Aug|Sept?|Okt|Nov|Dez|Früh|Herb)', month_tok, re.IGNORECASE):
            continue

        rest = ' '.join(tokens[tidx + 1:])
        rows.append({'jahr': year, 'monat': month_tok, 'detail': rest})

    return rows


def parse_chunk(chunk: dict) -> dict:
    raw = chunk['raw']

    # Unit name: first line
    first_line = raw.splitlines()[0].strip()
    # Strip trailing * and everything after it if * is mid-line
    name_line = re.sub(r'\s*\*.*', '', first_line).strip()

    # Pattern A: "20.Infanterie-Division" — number leads
    m_hdr = re.match(r'^(\d{1,3})\.\s*(.+)', name_line)
    if m_hdr:
        nummer = m_hdr.group(1)
        name_raw = m_hdr.group(2).strip()   # strip leading "20." prefix
    else:
        # Pattern B: "Feldersatz-Btl.20" — number at end
        # Extract the last number in range 15-30 as the unit number
        name_raw = name_line
        nums = re.findall(r'\b(\d{1,3})\b', name_line)
        nummer = next((n for n in reversed(nums) if 15 <= int(n) <= 30), '')

    # WK + FStO from (WK ...) line
    wehrkreis = ''
    heimatgarnison = ''
    m_wk = RE_WK_LINE.search(raw[:500])  # only look at start
    if m_wk:
        wehrkreis = m_wk.group(1).strip() if m_wk.group(1) else ''
        heimatgarnison = m_wk.group(2).strip() if m_wk.group(2) else ''

    # Formation info: either "* <date/text>..." or (no star) a date line after (WK...)
    aufgestellt = ''
    m_auf = RE_AUFGESTELLT.search(raw)
    if m_auf:
        aufgestellt = re.sub(r'\s+', ' ', m_auf.group(1)).strip()[:500]
    else:
        # No *, look for a date line after the (WK...) header line
        after_wk = re.search(r'\(WK[^\)]+\)\s*\n(.+)', raw)
        if after_wk:
            aufgestellt = re.sub(r'\s+', ' ', after_wk.group(1)).strip()[:300]

    # Gliederung
    gliederung_raw = ''
    m_g = RE_G.search(raw)
    if m_g:
        gliederung_raw = re.sub(r'\s+', ' ', m_g.group(1)).strip()

    # Short subordination (U:)
    ueberstellung_kurz = ''
    m_u = RE_U.search(raw)
    if m_u:
        ueberstellung_kurz = re.sub(r'\s+', ' ', m_u.group(1)).strip()

    # FStO (E:) — overrides WK line if more specific
    ersatz = ''
    m_e = RE_E.search(raw)
    if m_e:
        ersatz = re.sub(r'\s+', ' ', m_e.group(1)).strip()

    # Unterstellung table
    unterstellungen = []
    m_ub = RE_USTERZ_BLOCK.search(raw)
    if m_ub:
        unterstellungen = parse_unterstellung_table(m_ub.group(1))

    return {
        'nummer': nummer,
        'einheit': name_raw,
        'wehrkreis': wehrkreis,
        'heimatgarnison': heimatgarnison,
        'aufgestellt': aufgestellt,
        'gliederung': gliederung_raw,
        'ueberstellung_kurz': ueberstellung_kurz,
        'ersatz': ersatz,
        'unterstellungen': unterstellungen,
        '_raw_len': len(raw),
    }


# ── 4. main ───────────────────────────────────────────────────────────────────

def main():
    print("Schritt 1: Textextraktion …")
    pages = extract_pages(PDF_PATH)
    full_text = '\f'.join(pages)  # form-feed between pages
    print(f"  {len(pages)} Seiten, {len(full_text):,} Zeichen")

    print("Schritt 2: Chunk-Erkennung …")
    chunks = find_chunks(full_text)
    print(f"  {len(chunks)} Einträge erkannt")

    # Save debug chunks (raw text only, truncated for readability)
    debug = [{'offset': c['offset'], 'preview': c['raw'][:300]} for c in chunks]
    DEBUG_PATH.write_text(json.dumps(debug, ensure_ascii=False, indent=2))
    print(f"  → {DEBUG_PATH} geschrieben ({DEBUG_PATH.stat().st_size // 1024} KB)")

    print("Schritt 3: Strukturierte Extraktion …")
    records = [parse_chunk(c) for c in chunks]

    # QC
    with_table = sum(1 for r in records if r['unterstellungen'])
    without_table = len(records) - with_table
    print(f"\n── QC ──────────────────────────────")
    print(f"  Einträge gesamt:        {len(records)}")
    print(f"  Mit Unterstellungstab.: {with_table}")
    print(f"  Ohne:                   {without_table}")

    # Gold standard check: 20. Inf.Div. (mot.) / 20. Pz.Gren.Div.
    gold = [r for r in records if '20' in r['nummer'] and
            ('Infanterie' in r['einheit'] or 'Panzergrenadier' in r['einheit'])]
    if gold:
        print(f"\n  Gold-Standard-Check — 20. Inf.Div.(mot.) / 20.Pz.Gren.Div.:")
        for g in gold:
            print(f"    {g['nummer']}. {g['einheit']}")
            print(f"      WK: {g['wehrkreis']}, Garnison: {g['heimatgarnison']}")
            print(f"      Unterstellung-Einträge: {len(g['unterstellungen'])}")
            if g['unterstellungen']:
                for row in g['unterstellungen'][:3]:
                    print(f"        {row}")
    else:
        print("  WARNUNG: Kein Gold-Standard-Eintrag gefunden!")

    # Remove obvious false positives
    def is_valid_entry(r: dict) -> bool:
        # Bd. 4 covers units 15–30; numbers outside range are OCR artifacts
        try:
            n = int(r['nummer'])
            if not (15 <= n <= 30):
                return False
        except ValueError:
            return False
        return True

    filtered = [r for r in records if is_valid_entry(r)]
    removed = len(records) - len(filtered)
    if removed:
        print(f"  {removed} Außerhalb-Bereich-Einträge entfernt")

    print("Schritt 4: Ausgabe …")
    OUTPUT_PATH.write_text(json.dumps(filtered, ensure_ascii=False, indent=2))
    print(f"  → {OUTPUT_PATH} geschrieben ({OUTPUT_PATH.stat().st_size // 1024} KB)")
    print("Fertig.")


if __name__ == '__main__':
    main()
