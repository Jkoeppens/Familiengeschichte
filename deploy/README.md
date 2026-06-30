# Railway-Deployment

## Architektur

```
deploy/          ← Code-Image (in Git, wird gebaut)
  server.py
  db.py
  …

/data/           ← Railway Volume (persistent, nicht im Image)
  familiengeschichte.db
  stanford_borders_hires.pmtiles
  kz_lager.geojson
  ghettos_new.json
  operationen_wk2_new.json
  yahad_killing_sites_new.json
  gazeteer_cache.json          (wird zur Laufzeit angelegt/erweitert)
  nicht_aufgeloest.json        (wird zur Laufzeit angelegt)
```

## Setup-Reihenfolge (einmalig)

### 1. Volume anlegen und mounten

Im Railway-Dashboard:
- Service → Storage → "Add Volume"
- Mount Path: `/data`

### 2. Environment-Variablen setzen

```
DATA_DIR=/data
APP_PASSWORD=<dein-passwort>        # optional, aktiviert Login
FLASK_SECRET_KEY=<random-hex-32>    # openssl rand -hex 32
ANTHROPIC_API_KEY=<key>             # für PDF-Upload/Vision
GEONAMES_USER=<username>            # optional, für Geo-Fallback
```

### 3. Große Dateien ins Volume kopieren (einmalig nach erstem Deploy)

Die Dateien müssen einmalig aus dem Image-Bundle ins persistente Volume
kopiert werden. Dafür gibt es zwei Wege:

**Option A — Railway CLI:**

```bash
railway run --service <service-name> python3 -c "
import os, shutil
from pathlib import Path

CODE = Path('/app')   # Pfad des Images auf Railway
DATA = Path('/data')

files = [
    'familiengeschichte.db',
    'stanford_borders_hires.pmtiles',
    'kz_lager.geojson',
    'ghettos_new.json',
    'operationen_wk2_new.json',
    'yahad_killing_sites_new.json',
    'gazeteer_cache.json',
]
for f in files:
    src = CODE / f
    dst = DATA / f
    if src.exists() and not dst.exists():
        shutil.copy2(src, dst)
        print(f'kopiert: {f}')
    elif dst.exists():
        print(f'bereits vorhanden: {f}')
    else:
        print(f'FEHLT im Image: {f}')
"
```

**Option B — Init-Skript beim Start:**

In `Procfile` statt `web: gunicorn …` verwenden:

```
web: python3 init_volume.py && gunicorn server:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

`init_volume.py` prüft ob Dateien im Volume fehlen und kopiert sie aus dem
Image — so passiert die Init automatisch beim ersten Start.

## Lokaler Test

**Ohne DATA_DIR (normaler lokaler Betrieb):**
```bash
cd deploy/
python3 server.py
# → öffnet sqlite auf ./familiengeschichte.db, serviert GeoJSON aus ./
```

**Mit DATA_DIR (simuliert Railway-Volume):**
```bash
DATA_DIR=/tmp/test_volume python3 server.py
# → Fehler: "Folgende Datendateien fehlen in DATA_DIR=/tmp/test_volume"
# → sinnvolle Fehlermeldung + sys.exit(1) statt unklarem Crash
```

## Dateigrößen (Richtwert)

| Datei | Größe |
|---|---|
| `familiengeschichte.db` | ~40 MB |
| `stanford_borders_hires.pmtiles` | ~17 MB |
| `yahad_killing_sites_new.json` | ~6 MB |
| `ghettos_new.json` | ~841 KB |
| `kz_lager.geojson` | ~801 KB |
| `operationen_wk2_new.json` | ~206 KB |
| `gazeteer_cache.json` | ~200 KB |
