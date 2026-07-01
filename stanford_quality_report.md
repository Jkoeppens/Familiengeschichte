# Stanford GeoJSON — Qualitätsbericht

Quelle: `stanford_monthly/*.geojson` (73 Dateien, 1939-01 bis 1945-01)

---

## Schritt 4: Geometrie-Qualität

### Stichprobe

| Datei | Features | Invalide | Klein (<0.1°²) | Vertices | −simplify(0.05) | −simplify(0.1) |
|---|---|---|---|---|---|---|
| stanford_1939-01.geojson | 38 | 1 | 7 | 42 287 | −1.2 % | −1.6 % |
| stanford_1940-07.geojson | 36 | 1 | 7 | 42 483 | −1.2 % | −1.6 % |
| stanford_1942-01.geojson | 41 | 1 | 7 | 42 276 | −1.2 % | −1.6 % |
| stanford_1943-07.geojson | 39 | 1 | 7 | 42 265 | −1.2 % | −1.6 % |
| stanford_1945-01.geojson | 38 | 1 | 7 | 42 483 | −1.3 % | −1.6 % |

### Invalide Geometrien

**Exakt 1 pro Datei, immer dasselbe Feature: Norway** (MultiPolygon).  
Fehlerart: `Holes are nested` bei Koordinate `(8.236, 58.169)`.  
Das ist ein bekannter Topologie-Fehler bei komplexen Küstenlinien-Polygonen.

**Empfehlung**: `buffer(0)` oder `make_valid()` (Shapely ≥ 1.8) beim Laden anwenden:
```python
gdf.geometry = gdf.geometry.apply(lambda g: g if g.is_valid else g.buffer(0))
```

### Kleine Features

**7 Mikrostaat-/Territorien-Features pro Datei, alle konsistent:**

| Name | Fläche (°²) |
|---|---|
| Vatican | 0.00001 |
| Monaco | 0.00007 |
| Gibraltar | 0.00031 |
| San Marino | 0.00452 |
| Malta | 0.01891 |
| Liechtenstein | 0.01441 |
| Andorra | 0.01031 |

Alle haben `foreign_po = NaN` (keine Belegungsstatus-Information).  
Bei hohem Zoom-Level sichtbar, bei niedrigem Zoom verschwinden sie im Tile-Raster.  
**Kein Handlungsbedarf** — Tippecanoe filtert sie automatisch nach Mindestgröße pro Zoom-Level.

### Simplifizierung

Die Geometrien sind **bereits sehr kompakt**: Selbst `simplify(0.1)` (≈ 11 km Toleranz) reduziert die Vertices nur um **1.6 %**. Das bedeutet:

- Die Originaldaten sind mit ~42 000 Vertices/Datei gut vorverarbeitet.
- Vereinfachung bringt kaum Dateigrößenreduktion (ca. 1–2 % kleiner).
- **Keine Vorvereinfachung nötig** — Tippecanoe übernimmt Zoom-abhängige Simplifizierung intern.

---

## Schritt 5: Tool-Verfügbarkeit

| Tool | Status | Pfad / Version |
|---|---|---|
| `ogr2ogr` | ✅ installiert | `/opt/homebrew/bin/ogr2ogr` |
| `geopandas` | ✅ installiert | Version 1.1.3 |
| `tippecanoe` | ❌ fehlt | — |
| `pmtiles` (Python) | ❌ fehlt | — |

### Installation: Tippecanoe

Tippecanoe ist das Standardwerkzeug für GeoJSON → PMTiles / MBTiles:

```bash
brew install tippecanoe
```

### Installation: pmtiles Python-Modul (optional)

Wird für Python-seitige PMTiles-Inspektion/-Generierung gebraucht:

```bash
pip install pmtiles
```

---

## Empfehlung für die PMTiles-Konvertierung

**Bevorzugter Workflow: Tippecanoe**

```bash
# Alle 73 Monatsdateien in eine PMTiles-Datei
tippecanoe \
  --output=stanford_borders.pmtiles \
  --layer=borders \
  --attribute-type=ym:string \
  --minimum-zoom=2 \
  --maximum-zoom=8 \
  --drop-smallest-at-fraction=0.01 \
  --no-tile-size-limit \
  stanford_monthly/*.geojson
```

**Wichtig**: Tippecanoe fügt automatisch einen `tippecanoe-source-layer`-Tag ein; der Layer-Name muss im MapLibre-Style referenziert werden.

**Alternativer Workflow (ohne Tippecanoe): ogr2ogr → GeoPackage**

Falls PMTiles nicht möglich, können die 73 GeoJSON-Dateien zu einer einzigen GeoPackage-Datei konsolidiert werden:

```bash
# Erste Datei mit Ausgabedatei anlegen
ogr2ogr -f GPKG stanford_borders.gpkg stanford_monthly/stanford_1939-01.geojson -nln borders
# Alle weiteren anhängen
for f in stanford_monthly/stanford_1939-*.geojson stanford_monthly/stanford_19[4-5]*.geojson; do
  ogr2ogr -f GPKG -append stanford_borders.gpkg "$f" -nln borders
done
```

**Invalide Geometrien reparieren** (vor Konvertierung empfohlen):

```python
import geopandas as gpd
from pathlib import Path

for f in sorted(Path("stanford_monthly").glob("*.geojson")):
    gdf = gpd.read_file(f)
    gdf.geometry = gdf.geometry.apply(lambda g: g if g.is_valid else g.buffer(0))
    gdf.to_file(f"stanford_fixed/{f.name}", driver="GeoJSON")
```
