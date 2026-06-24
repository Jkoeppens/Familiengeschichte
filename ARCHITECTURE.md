# Projektarchitektur — Familiengeschichte Pipeline

Stand: 2026-06-24 | Branch: `pipeline`

---

## 1. Script-Übersicht

### Kern-Pipeline (Tessin)

#### `tessin_pipeline.py`
PDF-Extraktion für einen Tessin-Band (band-agnostisch).

| | |
|---|---|
| **Input** | `Bd_N_ocr.pdf` (via `--input`) |
| **Output** | `tessin_bdN.json`, `chunks_bdN_debug.json` |
| **Imports** | `pdfplumber`, `json`, `re`, `pathlib` |
| **Lokale Imports** | — |

Schritte: (1) Seitenextraktion + Header-Stripping, (2) Chunk-Erkennung via Stern-Datum-Signal (`* 26.8.1939`), (3) strukturiertes Parsing (nummer/einheit/wehrkreis/aufgestellt/unterstellungen), (4) QC-Filter.

---

#### `normalize_pipeline.py`
Normalisierung der Unterstellungstabellen (OCR-Fixes + Feldparsing).

| | |
|---|---|
| **Input** | `tessin_bdN.json` |
| **Output** | `tessin_bdN_clean.json` → `tessin_bdN_final.json` |
| **Imports** | `json`, `re`, `requests` (Ollama), `pathlib` |
| **Lokale Imports** | — |
| **Modi** | `--only-regex` (kein LLM), `--postprocess --finalize` |

Schritte: (1) Regex-OCR-Korrekturen (römische Zahlen, z.Vfg., Hgr-Varianten), (2) Feld-Parsing (korps/armee/hgr/theater/ort) via Regex-Fallback oder Ollama `llama3.1:8b`, (3) Post-Processing (deterministische Feldkorrekturen ohne LLM), (4) Umbenennung in `_final.json`.

---

#### `load_all_tessin.py`
Lädt alle 18 `tessin_bd*_final.json` in `familiengeschichte.db`.

| | |
|---|---|
| **Input** | `tessin_bd*_final.json` (alle im Verzeichnis) |
| **Output** | `familiengeschichte.db` — actors + events + participations |
| **Imports** | `db` (lokal) |
| **CLI** | `--band N` (einzelner Band) |

Erzeugt: `MilitaryUnit`-Actors, `UnitJoining`-Events (aus Unterstellungstabellen), `UnitNaming`-Events (aus Textfeldern mit "umbenannt in"), setzt `parent_unit_id` via strukturiertem DB-Lookup.

---

### Kern-Pipeline (Dokumente)

#### `pipeline_b.py`
Dokumenten-Ingestion für Bundesarchiv-Auskunftsschreiben und WASt-Karteikarten.

| | |
|---|---|
| **Input** | PDF (Bundesarchiv-Auskunft oder WASt-Karteikarte) |
| **Output** | `familiengeschichte.db` — Person-Actors + PersonJoining/Wounding/Hospitalization-Events |
| **Imports** | `pdfplumber`, `fitz` (PyMuPDF), `anthropic`, `jsonschema`, `db`, `abbreviations`, `geocode`, `entity_linking` |

Öffentliche Funktionen:
- `classify_pdf(path)` → `(typ, konfidenz)`
- `extract_bundesarchiv(path)` → strukturierte Personendaten + Einheitsmeldungen
- `ingest_bundesarchiv(path)` → Actor + PersonJoining-Events in DB
- `extract_wast(path)` → Seiten via Claude Vision (claude-opus-4-5)
- `ingest_wast(path)` → Wounding/Hospitalization/Missing-Events in DB

Event-Typen: `PersonJoining`, `Wounding`, `Hospitalization`, `Discharge`, `Missing`.

---

#### `entity_linking.py`
Verknüpft Einheitsnamen und Personennamen mit DB-Actors.

| | |
|---|---|
| **Input** | Einheitsname (string) + Jahr (int) |
| **Output** | `dict` mit actor_id, match_type, confidence, tessin_standort |
| **Imports** | `rapidfuzz`, `db` |

Öffentliche API:
- `link_unit(name, jahr)` — exakt → normalisiert → fuzzy (Schwelle 85)
- `link_person(name, birth_date)` — DB-Lookup oder neuer Actor
- `link_all(extraction_result)` — verknüpft ganzes Extraktionsergebnis
- `get_current_unit(person_id, zeitpunkt)` — Person → aktuelle Einheit
- `resolve_location(person_id, zeitpunkt)` — Stufenverortung: direkt → Einheit → unbekannt

---

### Datenbank

#### `db.py`
SQLite-Zugriff (Datei: `familiengeschichte.db`).

| | |
|---|---|
| **Input** | — (wird von allen anderen importiert) |
| **Imports** | `sqlite3`, `json`, `jsonschema`, `math`, `calendar` |
| **Schemas** | `schema/actor.schema.json`, `schema/event.schema.json`, `schema/participation.schema.json` |

Tabellen: `actors` (id, type, pref_label, data), `events` (id, type, time_begin, time_end, lat, lon, data), `participations` (event_id, actor_id, relation, role, data).

Öffentliche Funktionen:
- `insert_actor/event/participation()` — mit Schema-Validierung
- `verorte(actor_id, zeitpunkt)` — Events im Zeitraum
- `kontext(actor_id, zeitpunkt, radius_km)` — räumlicher Kontext (Haversine)
- `get_hierarchy(unit_id)` — Kette bis Armee/Heeresgruppe

---

### Hilfsmodule

#### `abbreviations.py`
Abkürzungsauflösung für WASt-Dokumente.

| | |
|---|---|
| **Input** | Freitext |
| **Output** | `{found: {abbrev: auflösung}, unresolved: [...]}` |
| **Datei** | `wast_abbreviations.json` |

---

#### `geocode.py`
Ortsnamensauflösung zu Koordinaten (hierarchisch).

| | |
|---|---|
| **Output** | `{lat, lon, precision, radius_km}` oder `None` |
| **Quellen** | Blacklist → interne `_GEO_EXTENDED`-DB → `gazeteer_historisch.json` → `gazeteer_regionen.json` → GeoNames API |
| **Cache** | `gazeteer_cache.json` |

---

### Orchestrierung

#### `batch_all_bands.py`
Batch-Pipeline für alle 18 Bände (Extraktion + Normalisierung + Finalisierung).

- Überspringt Bände mit bereits vorhandener `_final.json`
- `--extract-only`: nur Schritt 1 (kein LLM)

#### `run_overnight.sh`
Vollständiger Rebuild von Grund auf.

Schritte: alle PDFs → JSON → normalize (nur Regex) → finalize → DB leeren → `load_all_tessin.py` → Qualitätschecks.

---

### Datenlader (Einmalig / Speziell)

| Script | Zweck |
|---|---|
| `load_koppermann.py` | Koppermann-Referenzinstanz aus `actors.json + events.json + participations.json` in DB |
| `load_hierarchy.py` | Einheitshierarchien aus `gliederung`-Feldern → `UnitJoining`-Events + `parent_unit_id` |
| `load_a4.py` | Kontextereignisse (Schlachten, Verbrechen, KZ) aus JSON/GeoJSON; A4.2 auto-verknüpft Koppermann-Einheiten |
| `load_tessin_bd4.py` | Legacy-Loader für Bd. 4 (vor der einheitlichen Pipeline) |
| `normalize_with_llm.py` | OCR-Normalisierung + GeoNames-Lookup für ungelöste Ortsnamen in `nicht_aufgeloest.json` |
| `stanford_convert.py` | Konvertiert Stanford WWII-Grenzdaten (Shapefile → GeoJSON/PMTiles) |

---

### Infrastruktur

| Script | Zweck |
|---|---|
| `validate.py` | Schema-Validierung der DB-Inhalte; prüft Pflicht-IDs (Koppermann-Referenz) |
| `test_pipeline.py` | pytest-Tests für pipeline_b.py (17 Tests; B3-Tests brauchen ANTHROPIC_API_KEY) |
| `range_server.py` | HTTP-Server mit Range-Request-Support für PMTiles (`koppermann_karte.html`) |

---

## 2. Pipeline-Diagramm

```
Bd_N_ocr.pdf  (18 Bände, nicht im Git)
     │
     ▼
tessin_pipeline.py
     │  pdfplumber: Text-Extraktion + Header-Strip
     │  Chunk-Erkennung (Stern-Datum-Signal)
     │  Strukturiertes Parsing
     ▼
tessin_bdN.json
     │
     ▼
normalize_pipeline.py  [--only-regex | Ollama llama3.1:8b]
     │  Regex-OCR-Fixes (röm. Zahlen, z.Vfg., Hgr)
     │  Feld-Parsing: korps / armee / hgr / theater / ort
     ▼
tessin_bdN_clean.json
     │
normalize_pipeline.py --postprocess --finalize
     │  Deterministische Feldkorrekturen (kein LLM)
     ▼
tessin_bdN_final.json  (18 Dateien, committed)
     │
     ▼
load_all_tessin.py ──────────────────────────────────────┐
     │  MilitaryUnit actors                              │
     │  UnitJoining events (Unterstellungstabellen)      │
     │  UnitNaming events ("umbenannt in …")             │
     │  parent_unit_id via DB-Lookup                     │
     ▼                                                   │
familiengeschichte.db ◄─────────────────────────────────┘
     ▲                ▲                    ▲
     │                │                    │
load_a4.py    load_hierarchy.py    load_koppermann.py
(Kontextereignisse)  (Hierarchien)   (Referenzinstanz)

                  PDF (Bundesarchiv / WASt)
                          │
                          ▼
                    pipeline_b.py
                    ├── classify_pdf()
                    ├── extract_bundesarchiv()  ← pdfplumber + regex
                    │   └── abbreviations.py
                    ├── extract_wast()          ← Claude Vision (claude-opus-4-5)
                    │   └── abbreviations.py
                    └── ingest_*()
                        ├── entity_linking.link_unit()   ← rapidfuzz
                        ├── geocode._geocode()
                        └── db.insert_*()  [Schema-Validierung]
                                │
                                ▼
                    familiengeschichte.db
                    (Person actors + PersonJoining/Wounding/… events)
                                │
                                ▼
                    entity_linking.resolve_location()
                    (direkt → Einheit → unbekannt)
                                │
                                ▼
                    koppermann_karte.html
                    (range_server.py für PMTiles)
```

---

## 3. Abhängigkeiten

### Python-Pakete

| Paket | Gebraucht von | Status |
|---|---|---|
| `pdfplumber` | `tessin_pipeline.py`, `pipeline_b.py` | ✓ installiert |
| `fitz` (PyMuPDF) | `pipeline_b.py` (WASt Vision) | ✓ installiert |
| `anthropic` | `pipeline_b.py` (Claude Vision) | ✓ (API-Key nötig) |
| `jsonschema` | `db.py`, `pipeline_b.py`, `validate.py` | ✓ installiert |
| `rapidfuzz` | `entity_linking.py` | **✗ FEHLT** |
| `requests` | `normalize_pipeline.py` (Ollama) | ✓ (stdlib-Fallback: urllib) |
| `pytest` | `test_pipeline.py` | dev-dependency |

**Fehlende Installation:** `pip install rapidfuzz`
→ blockiert `entity_linking.py` und damit `pipeline_b.py` komplett.

### Dateien die existieren müssen

| Datei / Verzeichnis | Gebraucht von |
|---|---|
| `familiengeschichte.db` | alle Scripts via `db.py` (wird auto-erstellt) |
| `schema/*.schema.json` | `db.py` (Validierung) |
| `wast_abbreviations.json` | `abbreviations.py` |
| `gazeteer_historisch.json` | `geocode.py` |
| `gazeteer_regionen.json` | `geocode.py` |
| `gazeteer_cache.json` | `geocode.py` (wird auto-erstellt) |
| `tessin_bd*_final.json` (18 Stück) | `load_all_tessin.py` |
| `Bd_N_ocr.pdf` (18 PDFs) | `tessin_pipeline.py` — **nicht im Git** |
| `actors.json`, `events.json`, `participations.json` | `load_koppermann.py`, `validate.py` |
| `error_queue.json` | `pipeline_b.py` (wird auto-erstellt) |

### Externe Dienste

| Dienst | Gebraucht von | Pflicht? |
|---|---|---|
| Ollama `llama3.1:8b` auf `localhost:11434` | `normalize_pipeline.py` | Nein (`--only-regex` als Fallback) |
| Claude API (`ANTHROPIC_API_KEY`) | `pipeline_b.py` (WASt Vision) | Ja für WASt-Extraktion |
| GeoNames API (`GEONAMES_USER`) | `geocode.py`, `normalize_with_llm.py` | Nein (interne DB als Fallback) |

---

## 4. Bekannte Probleme / Offene TODOs

### Kritisch

- **`rapidfuzz` fehlt** — `entity_linking.py` schlägt bei Import fehl → `pipeline_b.py` ingestiert keine Dokumente.
  Fix: `pip install rapidfuzz`

### Architektur

- **`load_tessin_bd4.py`** ist ein Legacy-Script aus vor der einheitlichen Pipeline; es legt teilweise andere Actor-IDs an als `load_all_tessin.py`. Kann zu Dopplern führen wenn beide laufen.

- **`normalize_pipeline.py`** schreibt Intermediate-Datei `tessin_bdN_clean.json` — diese liegt nach `batch_all_bands.py` im Root und ist nicht archiviert (Archiv-Skript oben überträgt sie korrekt mit ins `tessin_archiv/`).

- **Ollama-Abhängigkeit** — `normalize_pipeline.py` ohne `--only-regex` hängt an lokalem Ollama. Timeout nach 20s, 2 Retries. Wird in `run_overnight.sh` explizit auf `--only-regex` gesetzt (LLM-freier Rebuild).

### Qualität

- **parent_unit_id-Auflösung** — `resolve_parent_id()` in `load_all_tessin.py` scheitert bei OCR-Artefakten im `pref_label` (> 70 Zeichen) und bei `unit_type = 'Unknown'`. Diese Actors bleiben ohne Hierarchieverknüpfung.

- **Fuzzy-Matching-Schwelle** — `_FUZZY_THRESHOLD = 85` in `entity_linking.py` führt zu False-Negatives bei stark abgekürzten WASt-Einheitsnamen (z.B. `"N.A. 20"` → kein Fuzzy-Match auf `"20. Nachrichten-Abteilung"`). Wird durch `UNIT_NORMALIZATIONS` teilweise abgefangen.

- **Geocoding-Lücken** — `nicht_aufgeloest.json` (494 einzigartige Namen, ~400 betroffene Events) nach Geocoding-Lauf vom 2026-06-24. Aktuell 75% geocodiert (3.832/5.086 UnitJoining-Events).

  Top-Probleme:
  - `'Hgr'`, `'Her'`, `'Lw.:'` → Abkürzungen, keine Orte → in `ORT_BLACKLIST` ergänzen
  - `'OKHHeimat'`, `'unbekannt"'` → OCR-Verschmelzungen → in `ORT_BLACKLIST`
  - `'Wiasma'` (5×), weitere echte Ostfront-Orte → in `gazeteer_historisch.json` eintragen

  Fix: `ORT_BLACKLIST` in `normalize_pipeline.py` erweitern,
  `gazeteer_historisch.json` um fehlende Ostfront-Orte ergänzen,
  dann `geocode.py --all` neu laufen lassen.
  Erwartet: ~400 zusätzliche Events geocodiert.

- **Umbenennung als verlorene Unterstellungszeilen** — `19.Grenadier-Division` (Bd. 4,
  Seite 126): Unterstellungstabelle steht nach dem Umbenennungsabsatz `19. Volks-Grenadier-Division`
  ohne eigenes `*`-Signal. `find_chunks()` erkennt keinen neuen Chunk → 4 Unterstellungszeilen
  verloren. Fix: Umbenennung (`„…wurde … umbenannt in …"` + nachfolgende `Unterstellung:`-Zeile)
  als Chunk-Signal erkennen (PENDING).

### Offen / In Arbeit

- `load_hierarchy.py` — Status unklar; Hierarchie-Events noch nicht systematisch für alle Bände erzeugt.
- `load_a4.py` — braucht `operationen_wk2.json`, `verbrechen_kontext.json`, `kz_lager.geojson`; Availability ungeprüft.
- `stanford_convert.py` — Einmalig für Kartendarstellung; shapefile-Daten (`EuropeanBorders_WWII/`) nicht im Git.
- `koppermann_karte.html` — Fertige Karte (main-Branch); Integration mit pipeline-Branch DB steht aus.
