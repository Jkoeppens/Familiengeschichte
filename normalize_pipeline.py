"""
Normalisierungs-Pipeline für Tessin-JSON → <band>_clean.json

Schritt 1: Regex-Korrekturen (deterministisch, kein LLM)
Schritt 2: LLM-Normalisierung (nur für Zeilen die nach Regex noch korrupt sind)
Schritt 3: Feld-Parsing (korps / armee / hgr / theater / ort) per LLM
Schritt 4: Ausgabe + Bericht

Verwendung:
    python3 normalize_pipeline.py                          # tessin_bd4.json (Standard)
    python3 normalize_pipeline.py --input tessin_bd1.json  # anderer Band
    python3 normalize_pipeline.py --sample 10              # nur erste 10 (Test)
    python3 normalize_pipeline.py --only-regex             # kein LLM, nur Regex-Pass
    python3 normalize_pipeline.py --postprocess            # Feldkorrekturen auf clean.json (kein LLM)
    python3 normalize_pipeline.py --postprocess --finalize # postprocess + in _final.json umbenennen
"""

import json, re, sys, time, requests
from pathlib import Path

# Zeilenweises Flushing — verhindert dass stdout komplett gebuffert wird
sys.stdout.reconfigure(line_buffering=True)

_DEFAULT_INPUT = Path('tessin_bd4.json')

OLLAMA_URL   = 'http://localhost:11434/api/generate'
OLLAMA_MODEL = 'llama3.1:8b'

# ── Schritt 1: Regex-Normalisierung ──────────────────────────────────────────

# Gültige vollständige römische Zahlen (Wehrmacht-Korps bis LXVI)
VALID_ROMAN = {
    'I','II','III','IV','V','VI','VII','VIII','IX','X',
    'XI','XII','XIII','XIV','XV','XVI','XVII','XVIII','XIX','XX',
    'XXI','XXII','XXIII','XXIV','XXV','XXVI','XXVII','XXVIII','XXIX',
    'XXX','XXXI','XXXII','XXXIII','XXXIV','XXXV','XXXVI','XXXVII',
    'XXXVIII','XXXIX',
    # Wehrmacht-Notation: XXXX statt XL (z.B. XXXXII = 42. Korps)
    'XXXXI','XXXXII','XXXXIII','XXXXIV','XXXXV','XXXXVI','XXXXVII','XXXXVIII','XXXXIX',
    'XL','XLI','XLII','XLIII','XLIV','XLV','XLVI',
    'XLVII','XLVIII','XLIX','L','LI','LII','LIII','LIV','LV','LVI',
    'LVII','LVIII','LIX','LX','LXI','LXII','LXIII','LXIV','LXV','LXVI',
    # SS-Korps (selten)
    'I.SS','II.SS','III.SS','IV.SS','V.SS','VI.SS','VII.SS',
    'XI.SS','XII.SS','XIII.SS',
    # Fallschirm
    'I.Fsch','I.Fs','I.Fallsch','I.Esch',
    # Luftwaffe
    'I.Lw','II.Lw','III.Lw','IV.Lw',
}

# Häufige Nicht-Korps-Erst-Tokens — für diese kein LLM-Aufruf nötig
KNOWN_NON_KORPS = {
    'z.Vfg.', 'z.Vfg', 'inAufst.', 'inAufst', 'i.Aufst.', 'i.Aufst',
    'verteilt', 'Verbleib', 'fehlt', 'Res.', 'BdE', 'OKH', 'OKW',
    'Heimat', 'Kreta', 'Befh.', 'W.Befh.', 'nichtgenannt',
    '(Rest)', '(Reste)', '(Kampfgr.)', '(Rgt.Gr.)', '(Stab)',
}

# Bekannte Eineindeutige OCR-Korrekturen (Reihenfolge wichtig: längste zuerst)
REGEX_RULES: list[tuple[str, str]] = [
    # 1. Mischung aus Groß/Kleinbuchstaben in einer romanischen Zahl
    #    XXXXlI → XXXXII,  xxlI → XXII,  xlI → XLI,  XXXxl → XXXXL
    (r'\bXXXXlI\b',       'XXXXII'),
    (r'\bXXXXl\b',        'XXXXII'),   # häufig in West-Frontkontext
    (r'\bXXXxl\b',        'XXXXL'),    # selten, aber eindeutig
    (r'\bxxlI\b',         'XXII'),
    (r'\bxlI\b',          'XLI'),
    (r'\bXlI\.SS\b',      'XII.SS'),
    # 2. Führendes Kleinbuchstaben-x vor Großbuchstaben-Sequenz
    #    xXIV → XXIV,  xXVI → XXVI,  xx → XX,  x → X
    (r'\bx([IVXLCDM][IVXLCDM]*)\b', r'X\1'),   # xXIV → XXIV
    (r'\b([IVXLCDM])x([IVXLCDM]+)\b', r'\1X\2'),  # XxXVI → XXXVI
    # 3. Einzelne gemischte Tokens mit erkennbarem Muster
    (r'\bXu\b',           'XII'),    # Xu → XII (häufiger als XI im Kontext)
    (r'\bvu\b',           'VII'),
    (r'\bVu\b',           'VII'),
    (r'\bvm\b',           'VII'),
    (r'\bVm\b',           'VIII'),
    (r'\bim\b',           'III'),    # im → III (m=OCR für II? selten)
    (r'\b([IVX]+)u\b',    r'\1I'),   # generell: nachfolgendes u → I
    # 4. Suffix-Artefakte: U≈II, O≈II, N≈I (OCR-Verwechslungen)
    (r'\bLIN\b',               'LIII'),       # LI+N(=II) → LIII  (spez. vor allgem. Regel)
    (r'\b([IVXLCDM]+)U\b',    r'\1II'),      # XXU→XXII, XXXXIU→XXXXIII, IU→III
    (r'\b([IVXLCDM]{3,})O\b', r'\1II'),      # XXXXVIO→XXXXVIII
    (r'\b([IVXLCDM]{3,})N\b', r'\1I'),       # XXXXVIIN→XXXXVIII, LVIN→LVII, XXXVIN→XXXVII
    # 5. z.Vfg.-Varianten — trailing Punkt wird konsumiert (verhindert z.Vfg..)
    (r'\bz[,.]V\s*f[ge][.,;]?',    'z.Vfg.'),
    (r'\bzZ?[NuU]\s*[fF][gGe]\.?', 'z.Vfg.'),
    (r'\bz\.Nfg\.?',               'z.Vfg.'),
    (r'\bZ\.Vfe\.?',               'z.Vfg.'),
    (r'\bz\.Vfe[,;]?',             'z.Vfg.'),
    # 6. Hgr-Varianten
    (r'\bHegr\.',   'Hgr.'),
    (r'\bHgre\.',   'Hgr.'),
    # 7. Allgemeine Bereinigung: xl → XL (wenn standalone)
    (r'\bxl\b',           'XL'),
    (r'\bxx\b',           'XX'),
    (r'\bx\b',            'X'),      # Einzelnes x → X
]

_COMPILED_RULES = [(re.compile(pat), repl) for pat, repl in REGEX_RULES]


def regex_normalize(detail: str) -> tuple[str, list[str]]:
    """Gibt (normalisierter_string, liste_der_Änderungen) zurück."""
    result = detail
    changes: list[str] = []
    for pattern, replacement in _COMPILED_RULES:
        new = pattern.sub(replacement, result)
        if new != result:
            changes.append(f'{pattern.pattern} → {replacement}')
            result = new
    return result, changes


def first_token_suspicious(detail: str) -> bool:
    """True wenn der erste Token vermutlich ein kaputtes Korps-Kürzel ist."""
    if not detail:
        return False
    tok = detail.split()[0]
    if tok in KNOWN_NON_KORPS:
        return False
    # Bekannte SS-/Lw-Suffixe
    base = re.sub(r'\.(SS|Lw|Fs|Fsch|Fallsch|Kav|Pz).*', '', tok)
    if base in VALID_ROMAN:
        return False
    # Wenn der Token nur aus Groß-Buchstaben/Punkte/Zahlen besteht → OK
    if re.match(r'^[\d\.]+', tok):   # Armee-direkt (z.B. "4.Armee")
        return False
    if re.match(r'^[A-ZÄÖÜ][a-zäöü]', tok):  # Wort mit normaler Groß-/Kleinschreibung
        return False
    # Verdächtig: Mischung aus Groß/Klein, einzelne Buchstaben, unbekannte Sequenz
    if re.search(r'[a-z]', tok) or (len(tok) <= 4 and re.match(r'^[A-Za-z]+$', tok) and tok not in VALID_ROMAN):
        return True
    return False


# ── Schritt 2 + 3: LLM-Normalisierung + Feld-Parsing ─────────────────────────

SYSTEM_PROMPT = """Du bist ein Experte für Wehrmacht-Dokumentation.
Ich gebe dir eine Zeile aus Tessin "Verbände und Truppen" — eine Unterstellungsangabe.
Format: [Korps] [Armee] [Heeresgruppe] [Schauplatz] [Ort]

Feldregeln (strikt):
- korps: Römische Zahl ggf. mit Suffix (z.B. "XIX", "XIV.Pz", "I.SS", "z.Vfg.")
- armee: Armee-Kürzel (z.B. "4.Armee", "1.Pz.Armee", "17.Armee", "Ob.Süd")
- hgr: NUR der Eigenname der Heeresgruppe — "Nord", "Mitte", "Süd", "A", "B", "E", "G" usw.
  NICHT "Osten"/"Westen" — das ist theater, nicht hgr!
- theater: Schauplatz/Frontrichtung — "Osten", "Westen", "Süden", "Heimat", "Südosten"
- ort: Ortsname oder Gebiet (z.B. "Polen", "Wolchow", "Süditalien", "Kreta")

Häufige OCR-Artefakte: xXIV→XXIV, xl→XL, vu→VII, Xu→XII, z.Vfe→z.Vfg., Hegr.→Hgr.
Antworte NUR mit einem JSON-Objekt, kein Text davor oder danach."""

PARSE_SCHEMA = '{"korps":"","armee":"","hgr":"","theater":"","ort":""}'


def ollama_parse(detail: str, retries: int = 2) -> dict:
    """Sendet detail an LLM und gibt geparste Felder zurück."""
    prompt = (
        f'{SYSTEM_PROMPT}\n\n'
        f'Unterstellungszeile: "{detail}"\n'
        f'JSON-Schema: {PARSE_SCHEMA}\n'
        f'Korrigiere OCR-Fehler und befülle alle Felder. '
        f'Leere Felder → leerer String. Antworte NUR mit JSON.'
    )
    for attempt in range(retries + 1):
        prefix = f'    LLM{"[Retry]" if attempt else ""}  {detail[:55]!r}'
        print(f'{prefix} …', end='', flush=True)
        t0 = time.time()
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={'model': OLLAMA_MODEL, 'prompt': prompt,
                      'stream': False, 'format': 'json'},
                timeout=20,
            )
            elapsed = time.time() - t0
            raw = resp.json().get('response', '{}')
            parsed = json.loads(raw)
            for k in ('korps', 'armee', 'hgr', 'theater', 'ort'):
                parsed.setdefault(k, '')
            print(f' {elapsed:.1f}s → korps={parsed.get("korps","?")} armee={parsed.get("armee","?")}')
            return parsed
        except requests.Timeout:
            elapsed = time.time() - t0
            print(f' TIMEOUT nach {elapsed:.0f}s (Versuch {attempt+1}/{retries+1})')
            if attempt < retries:
                time.sleep(1)
            else:
                return {'korps': '', 'armee': '', 'hgr': '', 'theater': '', 'ort': '',
                        '_error': 'Timeout', '_raw': detail}
        except json.JSONDecodeError as e:
            elapsed = time.time() - t0
            print(f' JSON-FEHLER nach {elapsed:.1f}s: {e}')
            if attempt < retries:
                time.sleep(1)
            else:
                return {'korps': '', 'armee': '', 'hgr': '', 'theater': '', 'ort': '',
                        '_error': str(e), '_raw': detail}
    return {}


# ── Regex-only field splitter (Fallback ohne LLM) ─────────────────────────────

RE_ARMEE = re.compile(
    r'(?:(\d+)\.)?\s*(?:(Pz|Geb|SS|Pz\.Gren)\.?)?\s*(Armee|Pz\.Armee|Pz\.Gru(?:ppe)?|Gru(?:ppe)?)',
    re.IGNORECASE,
)
RE_THEATER = re.compile(r'\b(Mitte|Nord|Süd|Nordukr|Südukr|Westen|Heimat|Osten|Süden|Südosten)\b')
RE_HGR = re.compile(
    r'Hgr\.?\s*[„""\']*\s*(Nord(?:ukraine)?|Mitte|Süd(?:ukraine)?|Weichsel|Kurland|Don|[A-H])\s*[„""\']*'
    r'|Heeresgruppe\s+(Nord(?:ukraine)?|Mitte|Süd(?:ukraine)?|[A-H])',
    re.IGNORECASE,
)

# Bekannte hgr-Varianten → kanonische Form
HGR_NORMALIZE: dict[str, str] = {
    'Nordukr.':    'Nordukraine',
    'Nordukr':     'Nordukraine',
    'Mittel':      'Mitte',
    'Süden':       '',      # Schauplatz-Richtung, kein HGr-Name
    'Osten':       '',
    'Westen':      '',
    'Her':         '',      # OCR-Artefakt
    'D*':          'D',     # Asterisk-Artefakt
    'Südukr':      'Südukraine',
    'Südukr.':     'Südukraine',
}

# ort-Werte die Theater-/Richtungsangaben sind, kein echter Ort
ORT_BLACKLIST: frozenset[str] = frozenset({
    'Osten', 'Westen', 'Ostfront', 'Westfront',
    'Ostpreußen allgemein', 'Russland allgemein', 'Frankreich allgemein',
    'unbekannt', '.', '-', '—',
})


_ORT_EXTRACT_BLACKLIST: frozenset[str] = frozenset({
    'Osten', 'Westen', 'Heimat', 'Süden', 'Norden',
    'Nord', 'Süd', 'Mitte', 'Don', 'Südosten',
    'Südwest', 'Südost',
})

_KLAMMER_NICHT_ORT: frozenset[str] = frozenset({
    'Auffr', 'Auffrischung', 'Reste', 'Rest',
    'Zitadelle', 'Kessel', 'Aufst', 'Aufstellung', 'Stab',
})


def extract_ort_from_right(detail_raw: str) -> str:
    """Extrahiert Ort als letztes nicht-geblacklistetes Token von rechts.

    Läuft unabhängig vom strukturierten Parse — greift nur wenn ort noch leer.
    'Mius (Taganrog)'  → 'Taganrog'  (Präzisierung = echter Ort)
    'Stalino (Auffr.)' → 'Stalino'   (Präzisierung = Truppenstatus → Hauptort)
    """
    scan = detail_raw
    m_klammer = re.search(r'\(([A-ZÄÖÜ][^)]*)\)\s*$', scan)
    if m_klammer:
        klammer_inhalt = m_klammer.group(1).strip('., ')
        if klammer_inhalt in _KLAMMER_NICHT_ORT:
            scan = scan[:m_klammer.start()].rstrip()

    tokens = scan.rstrip(')').rstrip().split()
    for token in reversed(tokens):
        token_clean = token.strip('.,)(')
        if (len(token_clean) > 2
                and token_clean not in _ORT_EXTRACT_BLACKLIST
                and re.match(r'^[A-ZÄÖÜ]', token_clean)
                and not token_clean.isupper()):  # Röm. Zahlen + Abkürzungen raus
            return token_clean
    return ''


MONAT_FIXES: dict[str, str] = {
    'Januarr': 'Januar', 'Februarr': 'Februar', 'Märzz': 'März',
    'Aprili': 'April', 'Junil': 'Juni', 'Julii': 'Juli',
    'Augustt': 'August', 'Septembert': 'September',
    'Oktoberr': 'Oktober', 'Novemberr': 'November', 'Dezemberr': 'Dezember',
}

_ROMAN_CHARS = frozenset('IVXLCDM')
_RE_ROMAN_DOT = re.compile(r'([IVXLCDM]+)\.([IVXLCDM]+)')

def fix_roman_ocr(s: str) -> str:
    """X.XI → XXI, XX.XI → XXXI usw. Nur wenn beide Teile reine Röm.-Zeichen sind."""
    def _replacer(m: re.Match) -> str:
        left, right = m.group(1), m.group(2)
        if all(c in _ROMAN_CHARS for c in left + right):
            return left + right
        return m.group(0)
    return _RE_ROMAN_DOT.sub(_replacer, s)


def regex_parse_fields(detail: str) -> dict | None:
    """Schneller Regex-Parser. Gibt None zurück wenn nicht eindeutig."""
    # Führende (Stab)/(Rest)/... vor dem Korps-Token entfernen
    detail_clean = re.sub(r'^\s*\([^)]+\)\s*', '', detail)
    tokens = detail_clean.split()
    if not tokens:
        return {'korps': '', 'armee': '', 'hgr': '', 'theater': '', 'ort': ''}

    korps = ''
    rest = detail_clean

    # Korps-Token: erster Token wenn gültige römische Zahl
    tok0 = tokens[0]
    base0 = re.sub(r'\.(SS|Lw|Fs|Fsch|Fallsch|Kav|Pz).*', '', tok0)
    if base0 in VALID_ROMAN or tok0 in VALID_ROMAN:
        korps = tok0
        rest = detail_clean[len(tok0):].strip()
    elif tok0 in KNOWN_NON_KORPS:
        korps = tok0   # z.Vfg. etc.
        rest = detail[len(tok0):].strip()
    else:
        return None    # erste Token unklar → LLM

    # Theater
    theater = ''
    m_th = RE_THEATER.search(rest)
    if m_th:
        theater = m_th.group(1)

    # Heeresgruppe
    hgr = ''
    m_hgr = RE_HGR.search(rest)
    if m_hgr:
        raw_hgr = (m_hgr.group(1) or m_hgr.group(2) or '').strip()
        # Ersten Buchstaben großschreiben (RE_HGR ist case-insensitive)
        hgr = raw_hgr[0].upper() + raw_hgr[1:] if raw_hgr else ''
    elif re.search(r'\bOKH\b', rest):
        hgr = 'OKH-Reserve'

    # Ort: letztes Wort/Phrase nach dem letzten bekannten Token
    ort = ''
    if m_th:
        after_theater = rest[m_th.end():].strip()
        candidate = after_theater.split()[0] if after_theater.split() else ''
        ort = '' if candidate in ORT_BLACKLIST else candidate

    # Armee: was zwischen korps und hgr/theater steht
    armee = ''
    m_arm = RE_ARMEE.search(rest)
    if m_arm:
        armee = m_arm.group(0).strip()

    return {'korps': korps, 'armee': armee, 'hgr': hgr, 'theater': theater, 'ort': ort}


# ── Haupt-Pipeline ─────────────────────────────────────────────────────────────

def normalize_entry(entry: dict, use_llm: bool = True) -> dict:
    """
    Normalisiert alle unterstellungen eines Eintrags.
    Gibt den geänderten Eintrag zurück (Original nicht mutiert).
    """
    if not entry.get('unterstellungen'):
        return entry

    new_entry = {**entry, 'unterstellungen': []}
    for row in entry['unterstellungen']:
        raw = row['detail']
        cleaned, regex_changes = regex_normalize(raw)

        # Feld-Parsing: erst Regex versuchen
        fields = regex_parse_fields(cleaned)
        llm_used = False

        if fields is None and use_llm:
            # Regex-Parser gescheitert → LLM
            fields = ollama_parse(cleaned)
            llm_used = True
        elif fields is None:
            fields = {'korps': '', 'armee': '', 'hgr': '', 'theater': '', 'ort': ''}

        # Ort immer von rechts bestimmen — überschreibt strukturierten Parse
        ort_fb = extract_ort_from_right(raw)
        if ort_fb:
            fields = {**fields, 'ort': ort_fb}

        new_row = {
            **row,
            'detail_raw': raw,
            'detail': cleaned,
            **fields,
            '_regex_changes': regex_changes,
            '_llm': llm_used,
        }
        new_entry['unterstellungen'].append(new_row)

    return new_entry


# ── Post-Processing: deterministische Feldkorrekturen ────────────────────────

def postprocess_row(row: dict) -> tuple[dict, list[str]]:
    """Wendet regelbasierte Fixes auf bereits geparste Felder an (kein LLM)."""
    changes: list[str] = []
    row = dict(row)
    # Nicht-String-Feldwerte normalisieren (LLM gibt gelegentlich int/None zurück)
    for _f in ('korps', 'armee', 'hgr', 'theater', 'ort', 'monat'):
        if _f in row and not isinstance(row[_f], str):
            row[_f] = str(row[_f]) if row[_f] is not None else ''
    detail = row.get('detail') or row.get('detail_raw', '')

    # Fix 1a: hgr aus Detail extrahieren wenn noch leer
    if not (row.get('hgr') or '').strip():
        m = RE_HGR.search(detail)
        if m:
            raw = (m.group(1) or m.group(2) or '').strip()
            hgr_new = raw[0].upper() + raw[1:] if raw else ''
            if hgr_new:
                row['hgr'] = hgr_new
                changes.append(f'hgr←regex: {hgr_new!r}')
        elif re.search(r'\bOKH\b', detail):
            row['hgr'] = 'OKH-Reserve'
            changes.append('hgr←OKH')

    # Fix 1b: hgr-Wert normalisieren
    hgr_cur = (row.get('hgr') or '').strip()
    if hgr_cur in HGR_NORMALIZE:
        hgr_new = HGR_NORMALIZE[hgr_cur]
        changes.append(f'hgr: {hgr_cur!r}→{hgr_new!r}')
        row['hgr'] = hgr_new

    # Fix 1c: Einzelbuchstabe / erstes Zeichen Kleinschreibung korrigieren
    hgr_cur = (row.get('hgr') or '').strip()
    if hgr_cur and hgr_cur[0].islower():
        fixed = hgr_cur[0].upper() + hgr_cur[1:]
        changes.append(f'hgr: {hgr_cur!r}→{fixed!r} (Großschreibung)')
        row['hgr'] = fixed

    # Fix 2: ort-Blacklist
    ort_cur = (row.get('ort') or '').strip()
    if ort_cur in ORT_BLACKLIST:
        changes.append(f'ort: {ort_cur!r}→""')
        row['ort'] = ''

    # Fix 2b: ort immer von rechts bestimmen — überschreibt strukturierten Parse
    raw_for_ort = (row.get('detail_raw') or row.get('detail') or '').strip()
    if raw_for_ort:
        ort_fb = extract_ort_from_right(raw_for_ort)
        if ort_fb:
            row['ort'] = ort_fb
            changes.append(f'ort←rechts: {ort_fb!r}')

    # Fix 3: Arabische Zahl fälschlich als korps-Wert
    korps_cur = (row.get('korps') or '').strip()
    if re.match(r'^\d+\.?$', korps_cur):
        armee_cur = (row.get('armee') or '').strip()
        if not armee_cur:
            row['armee'] = korps_cur.rstrip('.') + '.Armee'
            changes.append(f'armee←korps: {row["armee"]!r}')
        row['korps'] = ''
        changes.append(f'korps: {korps_cur!r}→"" (arabisch)')

    # Fix 4: Römische Zahl OCR-Artefakt im korps-Feld: X.XI → XXI, XX.XI → XXXI
    korps_cur2 = (row.get('korps') or '').strip()
    if korps_cur2:
        korps_fixed = fix_roman_ocr(korps_cur2)
        if korps_fixed != korps_cur2:
            changes.append(f'korps: {korps_cur2!r}→{korps_fixed!r} (roman_ocr)')
            row['korps'] = korps_fixed

    # Fix 5: Monat-Tippfehler aus OCR (Märzz → März etc.)
    monat_cur = (row.get('monat') or '')
    if monat_cur:
        monat_fixed = monat_cur
        for wrong, right_val in MONAT_FIXES.items():
            monat_fixed = monat_fixed.replace(wrong, right_val)
        if monat_fixed != monat_cur:
            changes.append(f'monat: {monat_cur!r}→{monat_fixed!r}')
            row['monat'] = monat_fixed

    if changes:
        row['_postprocess'] = changes
    return row, changes


def main():
    sample_mode      = '--sample' in sys.argv
    only_regex       = '--only-regex' in sys.argv
    resume           = '--resume' in sys.argv
    postprocess_mode = '--postprocess' in sys.argv
    finalize_mode    = '--finalize' in sys.argv
    sample_n    = int(sys.argv[sys.argv.index('--sample') + 1]) if sample_mode else None

    # Pfade: band-agnostisch via --input (Standard: tessin_bd4.json)
    _raw = Path(sys.argv[sys.argv.index('--input') + 1]) if '--input' in sys.argv else _DEFAULT_INPUT
    _stem = re.sub(r'_clean$', '', _raw.stem)
    input_path      = _raw.parent / f'{_stem}.json'
    output_path     = _raw.parent / f'{_stem}_clean.json'
    final_path      = _raw.parent / f'{_stem}_final.json'
    checkpoint_path = _raw.parent / f'{_stem}_clean_checkpoint.json'
    report_path     = _raw.parent / f'{_stem}_report.json'

    # ── Postprocess-Modus: Feldkorrekturen auf bereits verarbeitetes clean.json ─
    if postprocess_mode:
        print(f"Postprocessing: {output_path} (kein LLM)")
        if not output_path.exists():
            print(f"FEHLER: {output_path} nicht gefunden"); sys.exit(1)
        data = json.loads(output_path.read_text())

        st = {'zeilen': 0, 'geaendert': 0, 'felder': 0,
              'hgr_neu': 0, 'hgr_norm': 0, 'ort_geleert': 0,
              'korps_fix': 0, 'roman_fix': 0, 'monat_fix': 0}
        for entry in data:
            for j, row in enumerate(entry.get('unterstellungen', [])):
                st['zeilen'] += 1
                new_row, changes = postprocess_row(row)
                if changes:
                    entry['unterstellungen'][j] = new_row
                    st['geaendert'] += 1
                    st['felder']    += len(changes)
                    for c in changes:
                        if 'hgr←' in c:      st['hgr_neu']    += 1
                        if 'hgr:' in c:      st['hgr_norm']   += 1
                        if 'ort:' in c:      st['ort_geleert'] += 1
                        if 'arabisch' in c:  st['korps_fix']  += 1
                        if 'roman_ocr' in c: st['roman_fix']  += 1
                        if 'monat:' in c:    st['monat_fix']  += 1

        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

        print(f"\n── Diff-Bericht ──────────────────────────────")
        labels = {
            'zeilen':      'Zeilen gesamt',
            'geaendert':   'Zeilen geändert',
            'felder':      'Felder geändert',
            'hgr_neu':     'hgr neu gefüllt',
            'hgr_norm':    'hgr normalisiert',
            'ort_geleert': 'ort geleert (Blacklist)',
            'korps_fix':   'korps arabisch→leer',
            'roman_fix':   'korps roman OCR-Fix',
            'monat_fix':   'monat Tippfehler behoben',
        }
        for k, v in st.items():
            print(f"  {labels[k]:30s}: {v}")

        # Goldstandard-Ausgabe (nur wenn 20. Inf.Div. im Datensatz vorhanden)
        gold = next((r for r in data
                     if 'Infanterie-Division (mot.)' in r.get('einheit','')
                     and r.get('nummer') == '20'), None)
        if gold:
            print(f"\n── Goldstandard: {gold['einheit']} ──")
            for row in gold.get('unterstellungen', []):
                pp = '←PP' if row.get('_postprocess') else '    '
                print(f"  {pp} {row.get('jahr','?')}/{str(row.get('monat','?'))[:12]:12s} "
                      f"korps={row.get('korps',''):15s} armee={row.get('armee',''):20s} "
                      f"hgr={row.get('hgr',''):12s} theater={row.get('theater',''):10s} "
                      f"ort={row.get('ort','')[:22]}")

        if finalize_mode:
            import shutil
            shutil.move(str(output_path), str(final_path))
            print(f"\n  → {final_path} ({final_path.stat().st_size // 1024} KB)  [finalisiert]")
        else:
            print(f"\n  → {output_path} ({output_path.stat().st_size // 1024} KB)")
        return

    records = json.loads(input_path.read_text())
    if sample_mode:
        with_table = [r for r in records if r.get('unterstellungen')]
        subset = with_table[:sample_n]
        print(f"Sample-Modus: {len(subset)} Einträge mit Unterstellungstabelle")
    else:
        subset = records

    use_llm = not only_regex
    if not use_llm:
        print("Modus: Nur Regex (kein LLM)")

    # ── Resume: bereits verarbeitete Einträge aus Checkpoint laden ───────────
    results: list = []
    resume_from = 0
    if resume and checkpoint_path.exists():
        results = json.loads(checkpoint_path.read_text())
        resume_from = len(results)
        print(f"Resume: überspringe die ersten {resume_from} Einträge (aus Checkpoint)")

    # ── Schritt 2: Normalisierung ────────────────────────────────────────────
    stats = {'gesamt': len(subset), 'mit_tabelle': 0, 'zeilen_gesamt': 0,
             'regex_geloest': 0, 'llm_geloest': 0, 'fehler': 0,
             'nicht_benoetigt': 0}

    t_start = time.time()
    for i, entry in enumerate(subset):
        if i < resume_from:
            results_entry = results[i]
            # Statistik aus gecachtem Eintrag rekonstruieren
            for row in results_entry.get('unterstellungen', []):
                stats['zeilen_gesamt'] += 1
                if row.get('_llm'):
                    stats['fehler' if row.get('_error') else 'llm_geloest'] += 1
                elif row.get('_regex_changes'):
                    stats['regex_geloest'] += 1
                else:
                    stats['nicht_benoetigt'] += 1
            if results_entry.get('unterstellungen'):
                stats['mit_tabelle'] += 1
            continue

        if entry.get('unterstellungen'):
            stats['mit_tabelle'] += 1
            n_rows = len(entry['unterstellungen'])
            elapsed_total = time.time() - t_start
            print(f"\n[{i+1}/{len(subset)}] #{stats['mit_tabelle']} {entry['einheit'][:45]} "
                  f"({n_rows} Zeilen, +{elapsed_total:.0f}s seit Start)")

            t0 = time.time()
            norm_entry = normalize_entry(entry, use_llm=use_llm)
            elapsed = time.time() - t0

            for row in norm_entry['unterstellungen']:
                stats['zeilen_gesamt'] += 1
                if row.get('_llm'):
                    stats['fehler' if row.get('_error') else 'llm_geloest'] += 1
                elif row.get('_regex_changes'):
                    stats['regex_geloest'] += 1
                else:
                    stats['nicht_benoetigt'] += 1

            llm_n   = sum(1 for r in norm_entry['unterstellungen'] if r.get('_llm'))
            regex_n = sum(1 for r in norm_entry['unterstellungen'] if r.get('_regex_changes') and not r.get('_llm'))
            err_n   = sum(1 for r in norm_entry['unterstellungen'] if r.get('_error'))
            print(f"  → {elapsed:.1f}s | llm={llm_n} regex={regex_n} fehler={err_n}")

            results.append(norm_entry)
        else:
            results.append(entry)

        # Checkpoint alle 10 Einträge MIT Tabelle (nicht alle 100 Gesamt-Einträge)
        if stats['mit_tabelle'] > 0 and stats['mit_tabelle'] % 10 == 0:
            checkpoint_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
            print(f"  ✓ Checkpoint: {len(results)} Einträge, {stats['mit_tabelle']} mit Tabelle")

    # ── Schritt 3: Gold-Standard-Check ───────────────────────────────────────
    gold = next((r for r in results
                 if 'Infanterie-Division (mot.)' in r.get('einheit','')
                 and r.get('nummer') == '20'), None)
    gold_ok = False
    if gold and gold.get('unterstellungen'):
        first = gold['unterstellungen'][0]
        # Erwartung: Sept. 1939, XIX Korps, 4. Armee, Nord, Osten, Polen
        gold_ok = (
            first.get('korps', '').startswith('XIX')
            and '1939' in str(first.get('jahr', ''))
        )
    stats['goldstandard_20_pgd'] = 'OK' if gold_ok else 'FEHLER'

    # ── Ausgabe ───────────────────────────────────────────────────────────────
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    report_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2))

    total_elapsed = time.time() - t_start
    print(f"\n── Bericht ──────────────────────────────────")
    for k, v in stats.items():
        print(f"  {k:30s}: {v}")
    print(f"  {'laufzeit':30s}: {total_elapsed:.0f}s")
    print(f"\n  → {output_path} ({output_path.stat().st_size // 1024} KB)")
    print(f"  → {report_path}")


if __name__ == '__main__':
    main()
