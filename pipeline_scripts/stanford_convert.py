import geopandas as gpd
import json
from shapely.geometry import mapping, box, MultiPolygon, Polygon
from pathlib import Path

INPUT_DIR = Path('EuropeanBorders_WWII')
OUTPUT_FILE = Path('stanford_borders_all.geojson')
CLIP_BOX = box(-15, 35, 45, 65)
MIN_ISLAND_AREA = 2.0

HIGH_DETAIL = {
    'Germany', 'France', 'Belgium', 'Netherlands', 'Luxembourg',
    'Poland', 'General Government', 'Soviet Union',
    'Protectorate of Bohemia and Moravia', 'Slovakia',
    'Hungary', 'Romania', 'Bulgaria', 'Yugoslavia', 'Croatia',
    'Montenegro', 'Serbian Residual State', 'Serbia Residual State',
    'Italy', 'Switzerland', 'Greece', 'Turkey', 'Denmark',
    'Albania', 'Vichy France', 'Estonia', 'Latvia', 'Lithuania',
    'Danzig', 'Ukraine', 'White Russia', 'Byelorussia',
}

MONTHS = {
    'January': '01', 'February': '02', 'March': '03', 'April': '04',
    'May': '05', 'June': '06', 'July': '07', 'August': '08',
    'September': '09', 'October': '10', 'November': '11', 'December': '12',
}

def remove_small_islands(geom, min_area):
    if geom is None or geom.is_empty:
        return geom
    if isinstance(geom, Polygon):
        return geom
    if isinstance(geom, MultiPolygon):
        parts = [p for p in geom.geoms if p.area >= min_area]
        if not parts:
            return max(geom.geoms, key=lambda p: p.area)
        return parts[0] if len(parts) == 1 else MultiPolygon(parts)
    return geom

def parse_ym(stem):
    parts = stem.split('_')
    if len(parts) != 3 or parts[0] not in MONTHS:
        return None
    return f"{parts[2]}-{MONTHS[parts[0]]}"

shapefiles = sorted(INPUT_DIR.glob('*.shp'))
relevant = [
    shp for shp in shapefiles
    if parse_ym(shp.stem) and '1939-09' <= parse_ym(shp.stem) <= '1945-01'
]
print(f"Verarbeite {len(relevant)} Shapefiles …\n")

all_features = []

for shp in relevant:
    ym = parse_ym(shp.stem)
    try:
        gdf = gpd.read_file(shp).to_crs('EPSG:4326')
    except Exception as e:
        print(f"  {ym} FEHLER: {e}")
        continue

    gdf['geometry'] = gdf['geometry'].buffer(0)

    try:
        gdf = gpd.clip(gdf, CLIP_BOX)
    except Exception:
        gdf['geometry'] = gdf['geometry'].apply(
            lambda g: g.intersection(CLIP_BOX) if g and not g.is_empty else g
        )

    gdf['geometry'] = gdf['geometry'].apply(
        lambda g: remove_small_islands(g, MIN_ISLAND_AREA)
    )

    name_col = next((c for c in ('Name', 'NAME', 'name') if c in gdf.columns), None)
    fp_col   = next((c for c in ('Foreign_Po', 'FOREIGN_PO', 'foreign_po') if c in gdf.columns), None)

    def do_simplify(row):
        name = str(row[name_col]) if name_col else ''
        tol = 0.1 if name in HIGH_DETAIL else 0.6
        return row.geometry.simplify(tol, preserve_topology=True)

    gdf['geometry'] = gdf.apply(do_simplify, axis=1)
    gdf = gdf[~gdf['geometry'].is_empty & gdf['geometry'].notna()]

    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        name = str(row[name_col]) if name_col else ''
        fp   = str(row[fp_col])   if fp_col   else ''
        if fp in ('nan', 'None', '<Null>', ''):
            fp = 'Unknown'

        all_features.append({
            'type': 'Feature',
            'properties': {'ym': ym, 'name': name, 'foreign_po': fp},
            'geometry': mapping(geom),
        })

    print(f"  {ym}  {len(gdf):3d} features")

geojson = {'type': 'FeatureCollection', 'features': all_features}
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    json.dump(geojson, f, ensure_ascii=False, separators=(',', ':'))

size = OUTPUT_FILE.stat().st_size
print(f"\nFertig: {len(all_features)} Features total")
print(f"Dateigröße: {size/1024/1024:.1f} MB  ({'✓ Ziel erreicht' if size < 8*1024*1024 else '✗ zu groß'})")
