#!/usr/bin/env python3
"""Kopiert Datendateien ins Volume beim ersten Start."""
import shutil
from pathlib import Path

DATA_FILES = [
    'familiengeschichte.db',
    'stanford_borders_hires.pmtiles',
    'kz_lager.geojson',
    'ghettos_new.json',
    'operationen_wk2_new.json',
    'yahad_killing_sites_new.json',
    'yahad_killing_sites.csv',
]

APP_DIR = Path('/app')
DATA_DIR = Path('/data')

for filename in DATA_FILES:
    dest = DATA_DIR / filename
    src = APP_DIR / filename
    if not dest.exists() and src.exists():
        print(f'Kopiere {filename} → /data/', flush=True)
        shutil.copy2(src, dest)
    elif dest.exists():
        print(f'{filename} bereits vorhanden', flush=True)
    else:
        print(f'WARNUNG: {filename} nicht gefunden in /app', flush=True)
