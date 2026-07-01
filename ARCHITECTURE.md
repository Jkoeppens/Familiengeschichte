# Architektur — Familiengeschichte Pipeline

Stand: 2026-06-25 | Branch: `pipeline`

---

## Datenbankstand

`familiengeschichte.db` (SQLite, auto-erstellt via `db.py`):

| Tabelle | Einträge |
|---|---|
| actors | 15.707 |
| events | 5.481 |
| participations | 7.044 |

**Actors nach Typ:**

| type | Anzahl |
|---|---|
| MilitaryUnit | 15.703 (aus 18 Tessin-Bänden) |
| Person | 4 (Koppermann, Heinrich, Testmann, Prüfmann) |

**Events nach Typ:**

| type | Quelle | Anzahl |
|---|---|---|
| UnitJoining | tessin | 5.073 |
| UnitNaming | tessin | 376 |
| PersonJoining | bundesarchiv | 19 |
| DocumentCreation | bundesarchiv | 7 |
| Wounding | wast | 6 |

---

## Module

### `db.py` — Datenbankzugriff

Zentrale Schnittstelle zu `familiengeschichte.db`. Wird von allen anderen Modulen importiert.

**Schemas:** `schema/actor.schema.json`, `schema/event.schema.json`, `schema/participation.schema.json`

**Tabellen:**
- `actors (id, type, pref_label, data TEXT/JSON)`
- `events (id, type, time_begin, time_end, time_precision, lat, lon, data TEXT/JSON)`
- `participations (event_id, actor_id, relation, role, data TEXT/JSON)`

**Öffentliche Funktionen:**
- `insert_actor/event/participation(dict)` — mit jsonschema-Validierung
- `verorte(actor_id, zeitpunkt)` — alle Events des Akteurs zum Zeitpunkt, certainty DESC; Pfad 2: PersonJoining → Einheit → `get_hierarchy()` → UnitJoining mit Koordinaten
- `kontext(actor_id, zeitpunkt, radius_km=50)` — Events innerhalb radius_km um den Standort des Akteurs (Haversine)
- `get_hierarchy(unit_id)` — Kette `[unit_id, parent_id, …]` aufwärts bis Armee/Heeresgruppe; Fallback via UnitJoining-subordinate-Events

---

### `tessin_pipeline.py` — PDF-Extraktion

Extrahiert einen Tessin-Band (band-agnostisch) aus PDF in strukturiertes JSON.

| | |
|---|---|
| **Input** | `Bd_N_ocr.pdf` |
| **Output** | `tessin_bdN.json`, `chunks_bdN_debug.json` |
| **Imports** | `pdfplumber` |

Schritte: Seitenextraktion + Header-Stripping → Chunk-Erkennung (Stern-Datum-Signal `* 26.8.1939`) → strukturiertes Parsing (nummer / einheit / wehrkreis / aufgestellt / unterstellungen) → QC-Filter.

---

### `normalize_pipeline.py` — OCR-Normalisierung

Bereinigt die Unterstellungstabellen und parst Felder.

| | |
|---|---|
| **Input** | `tessin_bdN.json` |
| **Output** | `tessin_bdN_clean.json` → `tessin_bdN_final.json` |
| **Imports** | `json`, `re`, `requests` (Ollama), `pathlib` |

**Modi:**
- Standard: Regex-OCR-Fixes + Ollama `llama3.1:8b` für Feld-Parsing (korps/armee/hgr/theater/ort)
- `--only-regex`: kein LLM, nur deterministische Korrekturen
- `--postprocess [--finalize]`: deterministische Feldkorrekturen auf `_clean.json`, optional umbenennen in `_final.json`

Regex-Korrekturen: römische Zahlen (`IIl` → `III`), `z.Vfg.`, Heeresgruppen-Varianten, Jahres-Ligaturen.

---

### `normalize_with_llm.py` — Geo-Nachbearbeitung

OCR-Normalisierung und GeoNames-Nachschlag für ungelöste Ortsnamen aus `nicht_aufgeloest.json`.

| | |
|---|---|
| **Input** | `nicht_aufgeloest.json` |
| **Output** | aktualisiert `gazeteer_cache.json` + DB |
| **Imports** | `requests` (Ollama + GeoNames) |

Klassifiziert Namen als OCR-Artefakt / Org-Kürzel (→ Blacklist) oder Ort-Kandidat (→ Ollama `llama3.1:8b` → GeoNames).

---

### `load_all_tessin.py` — Tessin-Ingest

Lädt alle 18 `tessin_bd*_final.json` in `familiengeschichte.db`.

| | |
|---|---|
| **Input** | `tessin_bd*_final.json` |
| **Output** | `familiengeschichte.db` |
| **CLI** | `--band N` (einzelner Band) |

Erzeugt pro Einheit: `MilitaryUnit`-Actor mit `pref_label`, `alt_labels` (via `make_alt_labels()`), `tessin_band`, `parent_unit_id`. Aus Unterstellungstabellen: `UnitJoining`-Events mit Zeitraum, Ort, Koordinaten (via `geocode.py`). Aus Textfeldern: `UnitNaming`-Events ("umbenannt in …").

**`make_alt_labels(nummer, einheit)`:** erzeugt Suchvarianten — Abkürzungen expandiert, Nummer als Suffix und Prefix.

---

### `load_hierarchy.py` — Einheitshierarchie

Liest `gliederung`- und `ueberstellung_kurz`-Felder aus allen Tessin-Bänden, setzt `parent_unit_id` auf Child-Actors und legt `UnitJoining`-Unterstellungs-Events an.

---

### `load_a4.py` — Kontextereignisse

Lädt Schlachten, Verbrechen, KZ aus Kontext-JSONs in die DB.

| Quelle | Typ |
|---|---|
| `operationen_wk2.json` | Battle / Encirclement / Siege / Retreat / Surrender |
| `verbrechen_kontext.json` | Atrocity / MassExecution / GhettoOperation / Deportation |
| `kz_lager.geojson` | Atrocity (subtype: KZ) |

---

### `load_koppermann.py` — Koppermann-Referenzinstanz

Lädt `actors.json` (6 Actors: 3 Personen + 3 Units), `events.json`, `participations.json` in die DB. Testscript für `verorte()` und `kontext()`.

---

### `load_tessin_bd4.py` — Legacy-Loader Bd. 4

Älterer Loader für Band 4, vor der einheitlichen `load_all_tessin.py`-Pipeline entstanden. Legt dieselben Actor-IDs an, die `load_all_tessin.py` für Bd. 4 erzeugt.

---

### `pipeline_b.py` — Dokumenten-Ingestion

Verarbeitet Bundesarchiv-Auskunftsschreiben und WASt-Karteikarten (PDF) in DB-Events.

| | |
|---|---|
| **Input** | PDF |
| **Output** | Person-Actors + Events in `familiengeschichte.db` |
| **Imports** | `pdfplumber`, `fitz` (PyMuPDF), `anthropic`, `entity_linking`, `geocode`, `abbreviations`, `db` |

**Öffentliche Funktionen:**
- `classify_pdf(path)` → `(typ, konfidenz)` — Bundesarchiv vs. WASt
- `extract_bundesarchiv(path)` → strukturierte Personendaten + Einheitsmeldungen (pdfplumber + Regex)
- `ingest_bundesarchiv(path)` → Actor + PersonJoining-Events in DB; ruft `entity_linking.link_unit()` auf
- `extract_wast(path)` → Transkript via Claude Vision (`claude-opus-4-5`)
- `ingest_wast(path)` → Wounding / Hospitalization / Missing / Discharge-Events in DB

---

### `entity_linking.py` — Entitätsverknüpfung

Verknüpft Einheitsnamen und Personennamen mit DB-Actors.

| | |
|---|---|
| **Imports** | `rapidfuzz`, `db` |

**Öffentliche Funktionen:**
- `link_unit(name, jahr)` → `dict` mit `actor_id`, `pref_label`, `match_type`, `confidence`, `tessin_standort`
- `link_person(name, birth_date)` → `actor_id`
- `link_all(extraction_result)` → verknüpft gesamtes Extraktionsergebnis
- `get_current_unit(person_id, zeitpunkt)` → `dict|None`
- `resolve_location(person_id, zeitpunkt)` → Stufenverortung: direkt → Einheit → unbekannt

**`link_unit()` Matching-Stufen (Reihenfolge):**
1. Exakter Match auf `pref_label` oder `alt_labels`
2. Normalisiert (Sub-Einheiten strippen: "3./" u.ä.)
3. `UNIT_NORMALIZATIONS`-Tabelle (hardcodierte Kurznamen-Expansionen)
4. Fuzzy (rapidfuzz WRatio ≥ 88)

---

### `entity_linking.py` — Kanonisierung intern

`canonicalize.py` enthält `kanonisiere(name)` — normiert Abkürzungsschreibweisen auf Langform + arabische Zahl vor dem Matching.

---

### `geocode.py` — Ortsnamensauflösung

Löst Ortsnamen aus UnitJoining-Events zu `{lat, lon, precision, radius_km}` auf.

**Auflösungshierarchie:**
1. `SCHAUPLATZ_BLACKLIST` → `precision="schauplatz"`, keine Koordinaten
2. Interne `_GEO_EXTENDED`-DB (kompilierte ~3.000 Städte)
3. `gazeteer_historisch.json` — historische Namen mit modernen Koordinaten
4. `gazeteer_regionen.json` — Kriegsregionen als Zentroide
5. GeoNames API (wenn `GEONAMES_USER` gesetzt)
6. `nicht_aufgeloest.json` — ungelöste Namen loggen

**Cache:** `gazeteer_cache.json` — alle bisherigen Auflösungen.

---

### `abbreviations.py` — Abkürzungsauflösung

Löst militärische Abkürzungen in WASt-Dokumenten auf.

| | |
|---|---|
| **Input** | Freitext |
| **Output** | `{found: {abbrev: auflösung}, unresolved: [...]}` |
| **Datei** | `wast_abbreviations.json` |

---

### `server.py` — Flask-API-Server

Läuft auf Port 5050. Serviert statische HTML-Dateien und drei API-Endpoints.

**API-Endpoints:**

| Endpoint | Beschreibung |
|---|---|
| `GET /api/persons` | Alle Personen (`id`, `name`) |
| `GET /api/person/<id>/weg` | Verortete Events: direkte Koordinaten + `db.verorte()`-Lückenfüllung monatsweise |
| `GET /api/person/<id>/biografie` | `_DATA_BIOGRAFIE`-kompatibles Objekt: `{person, wast_ereignisse, einheitsmeldungen, dienstgrad}` |

`/weg` füllt Monate ohne direkte Koordinaten via `db.verorte()` auf (inferred=True).

---

### `validate.py` — Schema-Validierung

Prüft alle DB-Einträge gegen JSON-Schemas und validiert Pflicht-Referenzen.

| | |
|---|---|
| **Exit-Code** | 0 = alles ok, 1 = Fehler |
| **Schemas** | `schema/*.schema.json` |

---

### `test_pipeline.py` — pytest-Tests

17 Tests für `pipeline_b.py`. B3-Tests (WASt Vision) benötigen `ANTHROPIC_API_KEY`. Testdaten (PDFs) nicht im Git.

---

### Hilfsskripte

| Script | Zweck |
|---|---|
| `batch_all_bands.py` | Batch aller 18 Bände: Extraktion → Normalisierung → Finalisierung; überspringt vorhandene `_final.json` |
| `range_server.py` | HTTP-Server mit Range-Request-Support für PMTiles |
| `stanford_convert.py` | Shapefile (Stanford WWII Borders) → GeoJSON/PMTiles (Einmalig) |
| `compare_parse.py` | Vergleicht PDF-Rohtext mit geparsten Einträgen (`--band N --seite M`) |
| `run_overnight.sh` | Vollständiger Rebuild: alle PDFs → JSON → Regex-Normalize → DB-Reset → Load |

---

## Datenflusss

```
Bd_N_ocr.pdf  (18 Bände, nicht im Git)
     │
     ▼
tessin_pipeline.py
     │  Chunk-Erkennung (Stern-Datum-Signal)
     │  Parsing: nummer / einheit / wehrkreis / unterstellungen
     ▼
tessin_bdN.json
     │
     ▼
normalize_pipeline.py  [Regex + optional Ollama llama3.1:8b]
     │  OCR-Fixes, Feld-Parsing: korps/armee/hgr/theater/ort
     ▼
tessin_bdN_final.json  (18 Dateien, committed)
     │
     ▼
load_all_tessin.py ──────────────────────────────────────────┐
     │  MilitaryUnit-Actors + alt_labels                     │
     │  UnitJoining-Events (geocode.py → lat/lon)            │
     │  UnitNaming-Events                                     │
     │  parent_unit_id via DB-Lookup                          │
     ▼                                                        │
familiengeschichte.db ◄──────────────────────────────────────┘
     ▲                ▲                    ▲
     │                │                    │
load_a4.py    load_hierarchy.py    load_koppermann.py
(Kontextereignisse)  (Hierarchien)   (actors.json + events.json)

PDF (Bundesarchiv / WASt)
     │
     ▼
pipeline_b.py
     ├── classify_pdf()
     ├── extract_bundesarchiv()   ← pdfplumber + Regex
     │   └── abbreviations.py
     ├── extract_wast()           ← Claude Vision (claude-opus-4-5)
     │   └── abbreviations.py
     └── ingest_*()
         ├── canonicalize.kanonisiere()
         ├── entity_linking.link_unit()   ← rapidfuzz, 4 Stufen
         ├── geocode._geocode()
         └── db.insert_*()  [Schema-Validierung]
                  │
                  ▼
         familiengeschichte.db
         (Person-Actors + PersonJoining/Wounding/… Events)
                  │
                  ▼
         server.py (Flask, Port 5050)
         ├── /api/person/<id>/weg        ← db.verorte() + Lückenfüllung
         └── /api/person/<id>/biografie  ← wast_ereignisse + einheitsmeldungen
                  │
                  ▼
         stanford_test.html    — Hauptkarte: MapLibre + PMTiles + Biografie-Layer
         person_karte.html     — Personenspezifische Karte (URL-Param ?person_id=)
         koppermann_karte.html — Statische Referenzkarte (range_server.py für PMTiles)
```

---

## Kartendarstellung

| Datei | Beschreibung |
|---|---|
| `stanford_test.html` | Hauptkarte: MapLibre GL JS, Stanford-WWII-Grenzen via PMTiles, KZ/Ghettos/Schlachten als GeoJSON-Layer, Biografie-Layer (Wegpunkte + Trajektorie + Marker) per Personen-Dropdown |
| `person_karte.html` | Personenspezifische Karte; lädt Biografie via `GET /api/person/${id}/biografie` |
| `koppermann_karte.html` | Fertige statische Karte (main-Branch); Range-Requests via `range_server.py` |
| `stanford_simplify_test.html` | Testseite für PMTiles-Simplifizierungsvarianten |

**PMTiles:**
- `stanford_borders.pmtiles` — Stanford WWII-Grenzen (vereinfacht)
- `stanford_borders_hires.pmtiles` — höhere Auflösung

**Monats-GeoJSON:** `stanford_monthly/stanford_YYYY-MM.geojson` — ein File pro Monat (1939–1945).

---

## Schemas (`schema/`)

| Datei | Beschreibt |
|---|---|
| `actor.schema.json` | Person + MilitaryUnit (gemeinsames Schema, Pflichtfelder: `id`, `type`, `pref_label`) |
| `event.schema.json` | Alle Event-Typen; `place`, `source`, `time_span` als optionale Objekte |
| `participation.schema.json` | Verknüpfung event ↔ actor mit `relation` und `role` |

---

## Abhängigkeiten

### Python-Pakete

| Paket | Gebraucht von |
|---|---|
| `pdfplumber` | `tessin_pipeline.py`, `pipeline_b.py` |
| `fitz` (PyMuPDF) | `pipeline_b.py` (WASt Vision) |
| `anthropic` | `pipeline_b.py` (Claude Vision, `claude-opus-4-5`) |
| `jsonschema` | `db.py`, `pipeline_b.py`, `validate.py` |
| `rapidfuzz` | `entity_linking.py` |
| `flask` | `server.py` |
| `requests` | `normalize_pipeline.py` (Ollama), `geocode.py` (GeoNames) |
| `python-dotenv` | `pipeline_b.py` |

### Datendateien

| Datei | Gebraucht von |
|---|---|
| `schema/*.schema.json` | `db.py` |
| `wast_abbreviations.json` | `abbreviations.py` |
| `gazeteer_historisch.json` | `geocode.py` |
| `gazeteer_regionen.json` | `geocode.py` |
| `gazeteer_cache.json` | `geocode.py` (auto-erstellt) |
| `tessin_bd*_final.json` (18 Stück) | `load_all_tessin.py` |
| `actors.json` | `load_koppermann.py`, `validate.py` |
| `operationen_wk2.json` | `load_a4.py` |
| `verbrechen_kontext.json` | `load_a4.py` |
| `kz_lager.geojson` | `load_a4.py` |
| `stanford_borders.pmtiles` | `stanford_test.html`, `koppermann_karte.html` |
| `Bd_N_ocr.pdf` (18 PDFs) | `tessin_pipeline.py` — **nicht im Git** |

### Externe Dienste

| Dienst | Gebraucht von | Pflicht? |
|---|---|---|
| Ollama `llama3.1:8b` (`localhost:11434`) | `normalize_pipeline.py` | Nein (`--only-regex` als Fallback) |
| Claude API (`ANTHROPIC_API_KEY`) | `pipeline_b.py` (WASt Vision) | Ja für WASt-Extraktion |
| GeoNames API (`GEONAMES_USER`) | `geocode.py`, `normalize_with_llm.py` | Nein (interne DB als Fallback) |
