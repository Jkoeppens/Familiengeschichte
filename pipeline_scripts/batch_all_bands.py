"""
Batch-Pipeline: alle Tessin-Bände extrahieren, normalisieren, finalisieren.

Reihenfolge je Band:
  1. tessin_pipeline.py  --input Bd_X_ocr.pdf      (Extraktion, schnell)
  2. normalize_pipeline.py --input tessin_bdX.json  (LLM-Normalisierung, ~30 min)
  3. normalize_pipeline.py --input tessin_bdX.json --postprocess --finalize

Bd. 4 wird übersprungen wenn tessin_bd4_final.json bereits vorhanden ist.

Verwendung:
    python3 batch_all_bands.py              # alle fehlenden Bände
    python3 batch_all_bands.py --extract-only  # nur Schritt 1 (kein LLM)
"""

import subprocess, sys, time
from pathlib import Path

BANDS = [
    'Bd_1_ocr.pdf',
    'Bd_2_ocr.pdf',
    'Bd_3_ocr.pdf',
    'Bd_4_ocr.pdf',
    'Bd_5_ocr.pdf',
    'Bd_6_ocr.pdf',
    'Bd_7_ocr.pdf',
    'Bd_8_ocr.pdf',
    'Bd_9_ocr.pdf',
    'Bd_10_ocr.pdf',
    'Bd_11_ocr.pdf',
    'Bd_12_ocr.pdf',
    'Bd_13_ocr.pdf',
    'Bd_14_ocr.pdf',
    'Bd_15_ocr.pdf',
    'Bd_16-1_ocr.pdf',
    'Bd_16-2_ocr.pdf',
    'Bd_17_ocr.pdf',
]

EXTRACT_ONLY = '--extract-only' in sys.argv


def band_stem(pdf_name: str) -> str:
    """Bd_4_ocr.pdf → bd4,  Bd_16-1_ocr.pdf → bd16-1"""
    import re
    stem = Path(pdf_name).stem                         # Bd_4_ocr
    return re.sub(r'_ocr$', '', stem, flags=re.IGNORECASE).lower().replace('bd_', 'bd')


def run(cmd: list[str], label: str) -> bool:
    print(f"\n  ▶ {label}")
    print(f"    $ {' '.join(cmd)}")
    t0 = time.time()
    result = subprocess.run(cmd, text=True, capture_output=False)
    elapsed = time.time() - t0
    ok = result.returncode == 0
    status = "OK" if ok else f"FEHLER (exit {result.returncode})"
    print(f"    → {status}  ({elapsed:.0f}s)")
    return ok


def main():
    results = []
    t_start = time.time()

    for pdf_name in BANDS:
        pdf_path = Path(pdf_name)
        band = band_stem(pdf_name)
        raw_json   = Path(f'tessin_{band}.json')
        final_json = Path(f'tessin_{band}_final.json')

        print(f"\n{'═'*55}")
        print(f"  Band: {band}  ({pdf_name})")

        if not pdf_path.exists():
            print(f"  ✗ PDF nicht vorhanden — überspringe")
            results.append((band, 'kein_pdf'))
            continue

        if final_json.exists():
            print(f"  ✓ {final_json} bereits vorhanden — überspringe")
            results.append((band, 'bereits_fertig'))
            continue

        # Schritt 1: Extraktion
        ok = run(['python3', 'tessin_pipeline.py', '--input', str(pdf_path)],
                 f'Schritt 1: Extraktion → {raw_json}')
        if not ok:
            results.append((band, 'extraktion_fehler'))
            continue

        if EXTRACT_ONLY:
            results.append((band, 'extraktion_ok'))
            continue

        if not raw_json.exists():
            print(f"  ✗ {raw_json} nicht erzeugt — überspringe")
            results.append((band, 'extraktion_fehler'))
            continue

        # Schritt 2: LLM-Normalisierung
        ok = run(['python3', 'normalize_pipeline.py', '--input', str(raw_json)],
                 f'Schritt 2: Normalisierung (LLM)')
        if not ok:
            results.append((band, 'normalisierung_fehler'))
            continue

        # Schritt 3: Postprocessing + Finalisierung
        ok = run(['python3', 'normalize_pipeline.py', '--input', str(raw_json),
                  '--postprocess', '--finalize'],
                 f'Schritt 3: Postprocessing → {final_json}')
        results.append((band, 'fertig' if ok else 'postprocess_fehler'))

    # Abschlussbericht
    total = time.time() - t_start
    print(f"\n{'═'*55}")
    print(f"  Batch abgeschlossen in {total/60:.1f} min")
    print(f"\n  {'Band':12s}  {'Status'}")
    for band, status in results:
        icon = '✓' if status in ('fertig', 'bereits_fertig', 'extraktion_ok') else '✗'
        print(f"  {icon} {band:12s}  {status}")


if __name__ == '__main__':
    main()
