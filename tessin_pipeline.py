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

# Unit type keywords that appear in entry names
UNIT_TYPES = (
    r'Infanterie|Panzer(?:grenadier)?|Artillerie|Pionier(?:e)?|Grenadier|'
    r'Schützen|Jäger|Kavallerie|Gebirgs|Fallschirm|Luftlande|'
    r'Feld-Div(?:ision)?|Flak|Nachrichten|Versorgungs|'
    r'Ersatz|Reserve|Grenzschutz|Festungs|Sturm|Kampf|Schnell|Radfahr|'
    r'Sicherungs|Heeres|Signal|Eisenbahn|Brücken|Bau|Wach|'
    r'Generalkommando|Wehrkreis|Korps|Armee|Luftgau'
)

# Pattern: a number followed by a dot, optional spaces, then a unit type word
# Covers both "20.Infanterie-Division" and "20. Infanterie-Division"
RE_ENTRY_START = re.compile(
    rf'^(\d{{1,3}})\.\s*(?:{UNIT_TYPES})',
    re.MULTILINE | re.IGNORECASE,
)

# Fallback: anything with (WK on same or next line after a heading
RE_WK = re.compile(r'\(WK\s+[IVX]+', re.IGNORECASE)


def find_chunks(full_text: str) -> list[dict]:
    """Split full text into unit entry chunks using entry-start patterns.

    A true new entry must have a '*' formation date within 500 chars of the
    header line.  Sub-headings like '20.Panzergrenadier-Division' (renaming
    paragraphs inside a larger entry) don't have one, so they're skipped.
    """
    matches = list(RE_ENTRY_START.finditer(full_text))
    real_starts = []
    for m in matches:
        lookahead = full_text[m.start(): m.start() + 500]
        # Use only the header block (before first blank line) for star check
        first_blank = lookahead.find('\n\n')
        header_block = lookahead[:first_blank] if first_blank != -1 else lookahead[:300]
        # Remove lines that start a new sub-unit (contain "Rgt.", "Btl.", "Abt." + "*")
        # so that a "*" in a following sub-unit entry doesn't count
        header_lines = []
        for ln in header_block.splitlines():
            if re.match(r'\s*\w+[\.\-]\w+.*\*', ln) and header_lines:
                break  # stop at any line that looks like a new entry after the first
            header_lines.append(ln)
        header_clean = '\n'.join(header_lines)

        has_star = bool(
            re.search(r'\*\s*\d', header_clean)
            or re.search(r'\*\s*[A-Z]\w{2}', header_clean)  # "* Okt", "* Jan" etc.
        )
        # (WK ...) is also a reliable entry-header marker, within 200 chars
        has_wk = bool(re.search(r'\(WK\s+[IVX]', lookahead[:200]))
        # Skip cross-references ("15.Panzer-Grenadier-Division, siehe: ...")
        is_ref = bool(re.search(r'\bsiehe\b', lookahead[:80], re.IGNORECASE))
        if (has_star or has_wk) and not is_ref:
            real_starts.append(m)

    chunks = []
    for idx, m in enumerate(real_starts):
        start = m.start()
        end = real_starts[idx + 1].start() if idx + 1 < len(real_starts) else len(full_text)
        raw = full_text[start:end].strip()
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
    r'Unterstellung\s*:\s*\n(.*?)(?=\n(?:[A-Z][a-z]+ersatz|Feldersatz|\Z))',
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

    # Number + name
    m_hdr = re.match(r'^(\d{1,3})\.\s*(.+)', first_line)
    nummer = m_hdr.group(1) if m_hdr else ''
    name_raw = m_hdr.group(2).strip() if m_hdr else first_line

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
