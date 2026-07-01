#!/usr/bin/env python3
"""
compare_parse.py — Vergleicht PDF-Rohtext mit geparsten Einträgen.

Verwendung:
    python3 compare_parse.py --band 4 --seite 155
    python3 compare_parse.py --band 4 --einheit "Nachrichten-Abt. 20"
    python3 compare_parse.py --band 16-1 --seite 12
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

sys.path.insert(0, str(Path(__file__).parent))
try:
    from tessin_pipeline import is_running_header
except ImportError:
    def is_running_header(line: str) -> bool:
        return False


SEP = '═' * 58
MAX_EINHEIT_RESULTS = 10


# ── PDF-Zugriff ───────────────────────────────────────────────────────────────

def _extract_pages(pdf_path: Path) -> list[str]:
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ''
            lines = text.splitlines()
            start = 0
            for j in range(min(2, len(lines))):
                if is_running_header(lines[j]):
                    start = j + 1
            pages.append('\n'.join(lines[start:]))
    return pages


def _page_offsets(pages: list[str]) -> list[tuple[int, int, int]]:
    """(page_num_1based, start_char, end_char) — identisch zur Pipeline."""
    result = []
    pos = 0
    for i, page in enumerate(pages):
        result.append((i + 1, pos, pos + len(page)))
        pos += len(page) + 1  # +1 für '\f'-Trenner
    return result


def _page_num_for_offset(offsets: list[tuple], char_offset: int) -> int | None:
    for page_num, start, end in offsets:
        if start <= char_offset <= end:
            return page_num
    return None


# ── Dateipfade ────────────────────────────────────────────────────────────────

def _band_files(band: str) -> tuple[Path | None, Path | None, Path | None]:
    """Gibt (pdf_path, final_path, debug_path) zurück — None wenn nicht vorhanden."""
    stem = f"bd{band}"
    pdf   = Path(f"Bd_{band}_ocr.pdf")
    final = Path(f"tessin_{stem}_final.json")
    debug = Path(f"chunks_{stem}_debug.json")
    return (
        pdf   if pdf.exists()   else None,
        final if final.exists() else None,
        debug if debug.exists() else None,
    )


# ── Suche ─────────────────────────────────────────────────────────────────────

def _search_einheit(final: list[dict], query: str) -> list[dict]:
    q = query.lower()
    return [r for r in final if q in r.get('einheit', '').lower()]


def _records_for_page(final: list[dict], debug: list[dict],
                      offsets: list[tuple], page_num: int) -> list[dict]:
    """Alle final-Einträge deren Chunk-Offset auf diese Seite fällt."""
    info = next((o for o in offsets if o[0] == page_num), None)
    if not info:
        return []
    _, start, end = info

    chunks = [c for c in debug if start <= c['offset'] <= end]
    seen: set[int] = set()
    result: list[dict] = []
    for chunk in chunks:
        preview = chunk.get('preview', '')
        for rec in final:
            einheit = rec.get('einheit', '')
            # Mindestlänge verhindert False-Positives durch kurze Strings
            if einheit and len(einheit) >= 5 and einheit in preview[:350]:
                rid = id(rec)
                if rid not in seen:
                    seen.add(rid)
                    result.append(rec)
    return result


def _page_for_record(rec: dict, debug: list[dict],
                     offsets: list[tuple]) -> int | None:
    einheit = rec.get('einheit', '')
    if not einheit or len(einheit) < 5:
        return None
    for chunk in debug:
        if einheit in chunk.get('preview', '')[:350]:
            return _page_num_for_offset(offsets, chunk['offset'])
    return None


# ── Ausgabe ───────────────────────────────────────────────────────────────────

def _show_page(text: str, page_num: int, total: int) -> None:
    print(f"\n{SEP}")
    print(f"PDF ROHTEXT  (Seite {page_num} von {total})")
    print(SEP)
    print(text.strip() if text.strip() else '  (leer)')


def _show_parsed_header(label: str = 'GEPARST') -> None:
    print(f"\n{SEP}")
    print(label)
    print(SEP)


def _show_record(rec: dict) -> None:
    print(f"Einheit:      {rec.get('einheit', '')}")
    print(f"Nummer:       {rec.get('nummer', '')}")
    print(f"Wehrkreis:    {rec.get('wehrkreis', '')}")
    print(f"Heimatg.:     {rec.get('heimatgarnison', '')}")

    aufgest = (rec.get('aufgestellt') or '').strip()
    if aufgest:
        print(f"Aufgestellt:  {aufgest[:120]}")

    glieder = (rec.get('gliederung') or '').strip()
    if glieder:
        print(f"Gliederung:   {glieder[:100]}")

    ersatz = (rec.get('ersatz') or '').strip()
    if ersatz:
        print(f"Ersatz:       {ersatz[:80]}")

    ust = rec.get('unterstellungen', [])
    print(f"Unterstellungen ({len(ust)}):")
    if not ust:
        print("  — kein Eintrag —")
    else:
        for u in ust[:10]:
            jahr  = str(u.get('jahr')  or '?')
            monat = str(u.get('monat') or '?')
            korps = str(u.get('korps') or '')
            armee = str(u.get('armee') or '')
            hgr   = str(u.get('hgr')   or '')
            ort   = str(u.get('ort')   or '')
            print(
                f"  {jahr:4}/{monat:10}  "
                f"korps={korps:17} "
                f"armee={armee:22} "
                f"hgr={hgr:12} "
                f"ort={ort[:22]}"
            )
        if len(ust) > 10:
            print(f"  … {len(ust) - 10} weitere Zeilen")


# ── Hauptprogramm ─────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description='Vergleicht PDF-Rohtext mit geparsten Einträgen aus tessin_bdN_final.json'
    )
    ap.add_argument('--band', required=True,
                    help='Bandnummer, z.B. 4 oder 16-1')
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--seite', type=int, metavar='N',
                       help='Seitenzahl im PDF (1-basiert)')
    group.add_argument('--einheit', metavar='NAME',
                       help='Einheitsname oder Teilstring')
    args = ap.parse_args()

    pdf_path, final_path, debug_path = _band_files(args.band)

    if final_path is None:
        print(f"FEHLER: tessin_bd{args.band}_final.json nicht gefunden.", file=sys.stderr)
        sys.exit(1)
    final: list[dict] = json.loads(final_path.read_text(encoding='utf-8'))
    print(f"final.json:  {len(final)} Einträge")

    debug: list[dict] | None = None
    if debug_path:
        debug = json.loads(debug_path.read_text(encoding='utf-8'))
        print(f"debug.json:  {len(debug)} Chunks")
    else:
        print(f"HINWEIS: chunks_bd{args.band}_debug.json nicht gefunden — Seitenzuordnung nicht möglich.")

    pages: list[str] = []
    offsets: list[tuple] = []
    if not HAS_PDFPLUMBER:
        print("HINWEIS: pdfplumber nicht installiert — PDF-Rohtext nicht verfügbar.")
    elif pdf_path:
        print(f"Lade {pdf_path} … ", end='', flush=True)
        pages = _extract_pages(pdf_path)
        offsets = _page_offsets(pages)
        print(f"{len(pages)} Seiten")
    else:
        print(f"HINWEIS: Bd_{args.band}_ocr.pdf nicht gefunden — Rohtext nicht verfügbar.")

    # ── --seite ───────────────────────────────────────────────────────────────
    if args.seite is not None:
        page_num = args.seite

        if pages:
            if not (1 <= page_num <= len(pages)):
                print(f"FEHLER: Seite {page_num} liegt außerhalb 1–{len(pages)}.", file=sys.stderr)
                sys.exit(1)
            _show_page(pages[page_num - 1], page_num, len(pages))
        else:
            print(f"\n(PDF nicht verfügbar — Rohtext für Seite {page_num} kann nicht angezeigt werden)")

        # Einträge dieser Seite
        records: list[dict] = []
        if debug and offsets:
            records = _records_for_page(final, debug, offsets, page_num)
            if not records:
                # Angrenzende Seiten als Fallback (Chunk-Grenzen überlappen Seiten)
                for delta in (-1, 1, -2, 2):
                    alt = page_num + delta
                    records = _records_for_page(final, debug, offsets, alt)
                    if records:
                        _show_parsed_header(f'GEPARST (Einträge auf Seite {alt}, Seite {page_num} leer)')
                        break
                else:
                    _show_parsed_header(f'GEPARST (Seite {page_num})')
            else:
                _show_parsed_header(f'GEPARST ({len(records)} Einträge auf Seite {page_num})')
        else:
            _show_parsed_header(f'GEPARST (Seite {page_num})')

        if not records:
            print("  (keine Einträge für diese Seite gefunden)")
        else:
            for rec in records:
                print()
                _show_record(rec)

    # ── --einheit ─────────────────────────────────────────────────────────────
    else:
        matches = _search_einheit(final, args.einheit)
        if not matches:
            print(f"\nKeine Einträge für '{args.einheit}' in tessin_bd{args.band}_final.json.")
            sys.exit(1)

        total = len(matches)
        shown = matches[:MAX_EINHEIT_RESULTS]
        if total > MAX_EINHEIT_RESULTS:
            print(f"\n{total} Treffer für '{args.einheit}' — zeige erste {MAX_EINHEIT_RESULTS}:")
        else:
            print(f"\n{total} Treffer für '{args.einheit}':")

        for i, rec in enumerate(shown, 1):
            page_num: int | None = None
            if debug and offsets:
                page_num = _page_for_record(rec, debug, offsets)

            if pages and page_num:
                _show_page(pages[page_num - 1], page_num, len(pages))
            elif page_num:
                print(f"\n(PDF nicht verfügbar — Eintrag stammt aus Seite {page_num})")

            _show_parsed_header(f'GEPARST  [{i}/{total}]')
            print()
            _show_record(rec)


if __name__ == '__main__':
    main()
