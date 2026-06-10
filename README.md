# Kriegsweg Hans-Jürgen Koppermann 1939–1945

Interaktive Karte zum Kriegsweg von Hans-Jürgen Koppermann (geb. 02.09.1917 Hannover), Soldat der 20. Infanterie-Division (mot.) / 20. Panzergrenadier-Division, September 1939 bis Januar 1945.

**→ [Karte öffnen](https://jkoeppens.github.io/Familiengeschichte/koppermann_karte.html)**

## Inhalt

- `koppermann_karte.html` — vollständig eigenständige HTML-Karte (alle Daten eingebettet, kein Server nötig)
- `koppermann_biografie.json` — Primärquellen: WASt-Karte I/II, Bundesarchiv PA 2 2021/G-12837
- `einheiten_tessin.json` — Einheitsstandorte nach Tessin Bd. 4 (Sekundärquelle, Einheitsebene)
- `operationen_wk2.json` — Militäroperationen mit Koppermann-Relevanz
- `verbrechen_kontext.json` — Kriegsverbrechen und Holocaust-Ereignisse im Umfeld
- `kz_lager.geojson` — KZ- und Lager-Standorte (USHMM-Datensatz, bearbeitet)
- `stanford_borders_all.geojson` — Politische Grenzen 1939–1945 (Stanford, vereinfacht)
- `stanford_convert.py` — Konvertierungsskript: Stanford-Shapefiles → GeoJSON

## Datenquellen

| Datensatz | Quelle | Lizenz |
|---|---|---|
| Politische Grenzen | [Stanford Spatial History Project](https://github.com/nredick/stanford-geo-wwii) — De Groot (2010) | CC BY-NC |
| KZ- und Lagerdaten | [Holocaust Geographies Collaborative](https://www.ushmm.org/) — Knowles (2014), USHMM | Akademische Nutzung |
| Einheitsgeschichte | Tessin, Georg: *Verbände und Truppen der deutschen Wehrmacht und Waffen-SS 1939–1945*, Bd. 4 | — |
| Individualbiographie | Bundesarchiv, WASt: B 563-1 KARTEI/K-1458/033, PA 2 2021/G-12837 | — |

## Hinweise

- Die rohen Shapefiles (Stanford, USHMM) sind **nicht** im Repository enthalten (Größe / Lizenzbedingungen).
- Primärquellen (Bundesarchiv-Dokumente) sind ebenfalls nicht enthalten.
- Die Karte unterscheidet drei Evidenzstufen: **quellenbelegt** (WASt/Bundesarchiv), **Einheitsebene** (Tessin, gestrichelter Marker), **unbekannt**.
- Alle Koordinaten für Tessin-Einträge sind Zentroide des jeweiligen Operationsgebiets, keine individuellen Standorte.
