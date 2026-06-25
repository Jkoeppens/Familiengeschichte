"""
Tessin PDF → JSON pipeline (band-agnostisch).

Steps:
  1. Extract text page-by-page, strip running headers
  2. Detect unit-entry boundaries → chunks_<band>_debug.json
  3. Parse each chunk → structured record
  4. QC + output → tessin_<band>.json

Verwendung:
    python3 tessin_pipeline.py                         # Standard: Bd_4_ocr.pdf
    python3 tessin_pipeline.py --input Bd_1_ocr.pdf
    python3 tessin_pipeline.py --input Bd_16-1_ocr.pdf
"""

import pdfplumber
import json
import re
import sys
from pathlib import Path

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
RE_WK_HEADER = re.compile(r'\(?WK\s*[IVX]', re.IGNORECASE)

# Section/chapter lines to skip when looking backwards for a unit name
RE_SECTION = re.compile(
    r'^[A-Z]\.\s*(Infanterie|Schnell|Artillerie|Pionier|Nachrichten|Versorgungs|'
    r'Kraftfahr|Sanität|Feldjäger|Sicherungs|Luftwaffe|Waffen|Verbündete)',
    re.IGNORECASE,
)


_FIELD_LINE = re.compile(r'^[UEGKug]\s*:')


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
                or re.match(r'^[A-Z]\.\s+\w', s)
                or _FIELD_LINE.match(s))   # U:, E:, G:, K: field lines

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
        wk_m = RE_WK_HEADER.search(line)
        if not wk_m:
            continue
        # Inline case: "UnitName 15.10.1935 FStO Hamburg-Wandsbek, WKX."
        before_wk = line[:wk_m.start()].strip()
        if (before_wk
                and re.match(r'[A-ZÄÖÜ]', before_wk)
                and re.search(r'\d', before_wk)
                and not _FIELD_LINE.match(before_wk)
                and not line.strip().startswith('(')):
            chunk_starts.add(loff[i])
            continue
        # WK in E:/U:/G:-Feldzeilen ist kein Einheits-Signal
        if _FIELD_LINE.match(line.strip()):
            continue
        # Line-start case: WK on its own line — name is on a preceding line
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
MONAT_RE = re.compile(
    r'^(Jan|Febr?|Mär|Apr|Mai|Juni?|Juli?|Aug|Sept?|Okt|Nov|Dez|Früh|Herb)',
    re.IGNORECASE,
)
RE_USTERZ_ROW = re.compile(
    r'^(\d{4})?\s+'               # optional year
    r'(\w+(?:\./\w+)?)\s+'        # month(s), e.g. "Jan." or "Jan./Febr."
    r'(.+)$'                      # rest of line
)

RE_G = re.compile(r'\bG:\s*(.+?)(?=\nU:|\nE:|\nUnterstellung|\Z)', re.DOTALL)
RE_U = re.compile(r'\bU:\s*(.+?)(?=\nG:|\nE:|\nUnterstellung|\Z)', re.DOTALL)
RE_E = re.compile(r'\bE:\s*(.+?)(?=\nG:|\nU:|\nUnterstellung|\Z)', re.DOTALL)

# Parent-Unit-Extraktion: U:, Ug:, einzeilige Unterstellung:
PARENT_PATTERNS = [
    r'\bUg?:\s*([^\n;,]+)',
    r'\bUnterstellung:\s*([^\n;,]+)',
]


def extract_parent_unit(text: str) -> str | None:
    for pattern in PARENT_PATTERNS:
        m = re.search(pattern, text)
        if m:
            val = m.group(1).strip()
            if val:
                return val
    return None

RE_USTERZ_BLOCK = re.compile(
    r'Unterstellung\s*:\s*\n(.*?)(?=\n[A-Z][a-z]+ersatz|\nFeldersatz|\Z)',
    re.DOTALL,
)

_RE_INLINE_DATE = re.compile(r'\b(\d{1,2}\.\d{1,2}\.\d{4})\b')
_RE_INLINE_FSTO = re.compile(r'FStO\s+([^,;]+?)(?=\s*(?:[,;]|WK|$))')
_RE_INLINE_WK   = re.compile(r'\(?WK\s*([IVX]+)\)?\.?')


def clean_einheit(raw: str) -> tuple[str, str, str, str]:
    """Split inline-date entries: 'UnitName 15.10.1935 FStO Hamburg, WKX.' → (name, date, fsto, wk)."""
    if 'FStO' not in raw:
        return raw, '', '', ''
    m_date = _RE_INLINE_DATE.search(raw)
    if not m_date:
        return raw, '', '', ''
    name = raw[:m_date.start()].strip().rstrip(',.').strip()
    rest = raw[m_date.start():]
    aufgestellt    = m_date.group(1)
    m_fsto         = _RE_INLINE_FSTO.search(rest)
    m_wk           = _RE_INLINE_WK.search(rest)
    heimatgarnison = m_fsto.group(1).strip() if m_fsto else ''
    wehrkreis      = m_wk.group(1).strip()   if m_wk   else ''
    return name, aufgestellt, heimatgarnison, wehrkreis


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

        # Month token: prefix-match, OCR-Verschmelzungen (z.B. "Novemberwiederdurchdie") abschneiden
        month_tok = tokens[tidx]
        m = MONAT_RE.match(month_tok)
        if not m:
            continue
        monat = m.group(1) if len(month_tok) > 15 else month_tok

        rest = ' '.join(tokens[tidx + 1:])
        rows.append({'jahr': year, 'monat': monat, 'detail': rest})

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
        name_raw = name_line   # vollständigen Namen behalten inkl. führender Nummer
    else:
        # Pattern B: "Feldersatz-Btl.20" — number at end
        # Extract the last number in range 15-30 as the unit number
        name_raw = name_line
        nums = re.findall(r'\b(\d{1,3})\b', name_line)
        nummer = next((n for n in reversed(nums) if 15 <= int(n) <= 30), '')

    # Inline date/FStO/WK cleanup (e.g. "Nachrichten-Abt.20 15.10.1935 FStO Hamburg, WKX.")
    inline_aufgestellt = inline_heimatgarnison = inline_wehrkreis = ''
    if _RE_INLINE_DATE.search(name_raw):
        name_raw, inline_aufgestellt, inline_heimatgarnison, inline_wehrkreis = clean_einheit(name_raw)
        if not m_hdr:
            nums = re.findall(r'\b(\d{1,3})\b', name_raw)
            nummer = next((n for n in reversed(nums) if 15 <= int(n) <= 30), nummer)

    # Pattern B: trailing Nummer aus name_raw entfernen — wird separat in 'nummer' gespeichert
    # Nur Whitespace vor Nummer strippen, nicht Punkte (die Teil der Abkürzung sind: "Abt.20" → "Abt.")
    if not m_hdr and nummer:
        name_raw = re.sub(r'\s*\b' + re.escape(nummer) + r'\s*$', '', name_raw).rstrip()

    # WK + FStO from (WK ...) line
    wehrkreis = ''
    heimatgarnison = ''
    m_wk = RE_WK_LINE.search(raw[:500])  # only look at start
    if m_wk:
        wehrkreis = m_wk.group(1).strip() if m_wk.group(1) else ''
        heimatgarnison = m_wk.group(2).strip() if m_wk.group(2) else ''
    if not wehrkreis and inline_wehrkreis:
        wehrkreis = inline_wehrkreis
    if not heimatgarnison and inline_heimatgarnison:
        heimatgarnison = inline_heimatgarnison
    # WK-Fallback: wenn WKX. auf einer Folgezeile steht
    if not wehrkreis:
        m_wk2 = _RE_INLINE_WK.search(raw)
        if m_wk2:
            wehrkreis = m_wk2.group(1).strip()

    # Formation info: either "* <date/text>..." or (no star) a date line after (WK...)
    aufgestellt = ''
    m_auf = RE_AUFGESTELLT.search(raw)
    if m_auf:
        aufgestellt = re.sub(r'\s+', ' ', m_auf.group(1)).strip()
    elif inline_aufgestellt:
        aufgestellt = inline_aufgestellt
    else:
        # No *, look for a date line after the (WK...) header line
        after_wk = re.search(r'\(WK[^\)]+\)\s*\n(.+)', raw)
        if after_wk:
            aufgestellt = re.sub(r'\s+', ' ', after_wk.group(1)).strip()

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
        'ueberstellung_parent_name': extract_parent_unit(raw),
        'ersatz': ersatz,
        'unterstellungen': unterstellungen,
        '_raw_text': raw,
    }


# ── 4. QC filter + merge ──────────────────────────────────────────────────────

def is_valid_einheit(einheit: str) -> bool:
    if not einheit or len(einheit.strip()) < 5:
        return False
    e = einheit.strip()
    # Erlaubt: Großbuchstabe oder führende Zahl (z.B. "20.Infanterie-Division")
    if not e[0].isupper() and not e[0].isdigit():
        return False
    if ' ' not in e and '-' not in e and '.' not in e:
        return False
    # Ein einzelnes Wort das auf Punkt endet = Ortsname oder Fragment
    stripped = e.rstrip('.')
    if ' ' not in e and '-' not in e and '/' not in e and stripped.isalpha():
        return False
    # Zu lang = Fließtext-Fragment
    if len(e) > 60:
        return False
    # Enthält Satzzeichen die in Einheitsnamen nicht vorkommen
    if ':' in e or '=' in e:
        return False
    # Wehrkreis-Fragmente aus U:/E:-Zeilen
    if re.fullmatch(r'WK\s+[IVXLC]+\.?', e.strip()):
        return False
    return True


def merge_invalid_chunks(records: list[dict]) -> tuple[list[dict], int]:
    """Ungültige Chunks an den _raw_text des Vorgängers anhängen statt verwerfen.

    Gibt (merged_records, anzahl_angehängt) zurück.
    """
    merged: list[dict] = []
    appended = 0
    for rec in records:
        if not is_valid_einheit(rec.get('einheit', '')):
            if merged:
                merged[-1]['_raw_text'] += '\n' + rec.get('_raw_text', rec.get('raw', ''))
                appended += 1
            # kein Vorgänger → wirklich verwerfen
        else:
            merged.append(rec)
    return merged, appended


# ── 5. main ───────────────────────────────────────────────────────────────────

def main():
    # Pfade band-agnostisch aus --input ableiten
    _raw = Path(sys.argv[sys.argv.index('--input') + 1]) if '--input' in sys.argv else Path('Bd_4_ocr.pdf')
    _band = re.sub(r'_ocr$', '', _raw.stem, flags=re.IGNORECASE).lower().replace('bd_', 'bd')
    pdf_path    = _raw
    debug_path  = _raw.parent / f'chunks_{_band}_debug.json'
    output_path = _raw.parent / f'tessin_{_band}.json'

    print(f"Band: {_band}  ({pdf_path})")
    print("Schritt 1: Textextraktion …")
    pages = extract_pages(pdf_path)
    full_text = '\f'.join(pages)
    print(f"  {len(pages)} Seiten, {len(full_text):,} Zeichen")

    print("Schritt 2: Chunk-Erkennung …")
    chunks = find_chunks(full_text)
    print(f"  {len(chunks)} Einträge erkannt")

    debug = [{'offset': c['offset'], 'preview': c['raw'][:300]} for c in chunks]
    debug_path.write_text(json.dumps(debug, ensure_ascii=False, indent=2))
    print(f"  → {debug_path} geschrieben ({debug_path.stat().st_size // 1024} KB)")

    print("Schritt 3: Strukturierte Extraktion …")
    records = [parse_chunk(c) for c in chunks]

    filtered, appended = merge_invalid_chunks(records)
    removed = len(records) - len(filtered) - appended

    with_table = sum(1 for r in filtered if r['unterstellungen'])
    print(f"\n── QC ──────────────────────────────")
    print(f"  Einträge gesamt:        {len(records)}")
    print(f"  Gültig (nach Filter):   {len(filtered)}  ({removed} verworfen, {appended} angehängt)")
    print(f"  Mit Unterstellungstab.: {with_table}")

    print("Schritt 4: Ausgabe …")
    output_path.write_text(json.dumps(filtered, ensure_ascii=False, indent=2))
    print(f"  → {output_path} ({output_path.stat().st_size // 1024} KB)")
    print("Fertig.")


if __name__ == '__main__':
    main()
