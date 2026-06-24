# Bauplan: Familiengeschichte-Pipeline
## Revidiert nach CIDOC-CRM/WarSampo-Architektur

**Drei Grundprinzipien:**
1. Referenzdaten vor Inputdaten — Kontext muss stehen bevor ein erster Input durchläuft
2. Pipeline vor Testdaten — Pipeline wird gegen Koppermann getestet, nicht für ihn gebaut
3. Kein Schritt produziert Daten die manuell korrigiert werden müssen bevor der nächste Schritt sinnvoll ist

---

## Phase A: Referenzdatenbank aufbauen
*Einmalig. Ändert sich nur wenn neue Referenzquellen hinzukommen.*

### A1. Schema und Validierung
- [x] `SCHEMA.md` — menschenlesbarer Datenvertrag
- [x] `schema/actor.schema.json` — JSON Schema für Akteure
- [x] `schema/event.schema.json` — JSON Schema für Events
- [x] `schema/participation.schema.json` — JSON Schema für Beteiligungen
- [x] `validate.py` — Validierungsscript, läuft nach jeder Pipeline
- [x] `db.py` — SQLite-Modul mit `init_db()`, `insert_*()`, `verorte()`, `kontext()`
- [x] `familiengeschichte.db` — Datenbankdatei angelegt

### A2 — Architekturprinzip: Rohtext erhalten

Inspiriert von WarSampo (Hyvönen et al. 2016) und modernen Document-Parsing-Pipelines
(Impresso/impresso-text-acquisition, 2024): Parsing erfolgt in zwei getrennten Stufen.

**Stufe 1 — Struktur erhalten (tessin_pipeline.py):**
- Vollständiger Rohtext pro Einheit in `_raw_text`
- Alle erkannten Felder als best-effort, keine Längenbegrenzungen
- Nichts verwerfen — unverstandener Text bleibt in `aufgestellt` erhalten

**Stufe 2 — Schema befüllen (normalize_pipeline.py + load_all_tessin.py):**
- Strukturierte Felder aus `_raw_text` via Regex oder LLM
- Mehrere Durchläufe möglich ohne Rohdaten zu verlieren
- Verbesserungen an Stufe 2 ändern nie Stufe 1

---

### A2. Tessin → Einheitsdatenbank
- [x] Alle 18 Bände heruntergeladen und finalisiert
- [x] OCR-Text extrahiert, Chunks erkannt; `_raw_text` vollständig erhalten
- [x] `merge_invalid_chunks` aktiv — 0 verworfen, Anhänge an Vorgänger-Chunk
- [x] LLM-Normalisierung der Unterstellungstabellen (korps/armee/hgr)
- [x] Postprocessing: römische Zahlen, Monatstippfehler, Blacklist
- [x] Alle 18 Bände in DB geladen
      (15.726 Actors | 5.086 UnitJoining-Events)
- [x] `make_pref_label` konsistentes Format (`'20. Infanterie-Division'` mit Space)
- [x] `parent_unit_id` korrekt — `unit_20_nachrichten_abt_20` → `unit_20_pz_gren_div` ✓
- [x] A2.1 — Bd. 16-x: strukturell leer (Feldpostnummern/Ersatz-Einheiten ohne Unterstellungstabellen), dokumentiert
- [ ] A2.2 — Einheitshierarchie: `get_hierarchy()` in `db.py` (Kompanie → Division → Korps)
      Aus Tessin-Gliederungsfeldern extrahieren, Lücken dokumentieren
- [ ] A2.3 — Baseline-Qualitätsbericht `tessin_all_quality.md`

### A3. Gazeteer → Ortsauflösung
- [x] Geocoding-Lauf abgeschlossen: **75% geocodiert** (3.832 / 5.086 UnitJoining-Events)
- [x] 369 Schauplatz-Namen korrekt leer (Frankreich, Ostfront usw.)
- [x] 587 unaufgelöste Namen in `nicht_aufgeloest.json` dokumentiert
- [x] `validate.py`: alle Checks grün, alle Koppermann-Referenzinstanzen vorhanden
- [ ] Manuelle Nachpflege: häufige Orte aus `nicht_aufgeloest.json` in `gazeteer_historisch.json`
- [ ] Ziel: >85% Geocoding-Abdeckung

### A4. Kontextereignisse laden
- [ ] `operationen_wk2.json` → Battle-Events in DB
- [ ] `verbrechen_kontext.json` → Atrocity-Events in DB
- [ ] `kz_lager.geojson` → Atrocity-Events (Typ: KZ) mit Eröffnungs-/Schließungszeitraum
- [ ] Automatische Beteiligungsverknüpfung:
      Welche Einheiten waren laut Tessin zur selben Zeit im selben Raum?
      → `occurred_in_presence_of` wenn Zeitraum + Ort überlappen
      → `had_participant` wenn explizit in Quelle belegt
- [ ] 10 Stichproben manuell prüfen
- [ ] `kontext("unit_20_pz_gren_div", "1941-07", radius_km=200)` muss
      Minsk-Ghetto mit `occurred_in_presence_of` zurückgeben

---

## Phase B: Pipeline bauen
*Das eigentliche Produkt. Verarbeitet beliebige Inputdokumente.*

### B1. Dokumenttyp-Erkennung
- [ ] Automatische Klassifikation hochgeladener Dokumente:
      - WASt-Zentralkarteikarte (Karte I / Karte II)
      - Bundesarchiv-Auskunftsschreiben
      - Lazarettbuch-Eintrag
      - Sonstiges
- [ ] Konfidenzwert pro Klassifikation
- [ ] Fallback: manuelle Typauswahl

### B2. Extraktion — maschinengeschriebene Dokumente
- [ ] OCR für Auskunftsschreiben
- [ ] Personen disambiguieren (Koppermann vs. Heinrich im selben Dokument)
- [ ] Einheitsliste extrahieren: Name, Signatur, Jahr
- [ ] Output: `PersonJoining`-Events + Einheitsreferenzen im Schema

### B3. Extraktion — Handschrift (WASt-Karteikarten)
- [ ] LLM-Vision (Claude) statt klassisches OCR
- [ ] Strukturierte Felder: Name, Geburt, Truppenteil, Dienstgrad, Erkennungsmarke
- [ ] Meldungszeilen einzeln: Datum, Ereignistyp, Ort, Diagnose, Lkb.
- [ ] Unsichere Stellen markieren (`certainty` entsprechend setzen)
- [ ] Qualitätsprüfung: wie viele Felder korrekt vs. Koppermann-Goldstandard

### B4. Abkürzungsauflösung
- [ ] WASt-Abkürzungsverzeichnis → maschinenlesbare JSON-Datei
      (Basis: Bundesarchiv PDF Stand 01.10.2020)
- [ ] Militärische Abkürzungen (N.A., I.R., Pz.Gren.Rgt. usw.)
- [ ] Medizinische Abkürzungen (Gr.Spli.Verl., Rela., Lkb. usw.)
- [ ] Alle Abkürzungen im transkribierten Text identifizieren
- [ ] Nicht aufgelöste flaggen → Nutzer zur manuellen Klärung
- [ ] Erweiterbar: Nutzer kann eigene Abkürzungen ergänzen

### B5. Entity-Linking (Person → Einheit → Tessin)
- [ ] Einheitsnamen aus Extraktion normalisieren
      (Schreibvarianten → kanonische ID in DB)
- [ ] Einheitshierarchie auflösen:
      11. Kp. I.R. 90 → I.R. 90 → 20. Inf.Div.(mot.)
- [ ] Zeitraum der Meldung auf Tessin-Unterstellung mappen
- [ ] Sicherheitsstufen automatisch vergeben:
      - `certainty: 5` — WASt mit Datum und Ort
      - `certainty: 4` — Bundesarchiv, Jahr ohne Monat
      - `certainty: 3` — Tessin-Einheitsstand
      - `certainty: 2` — entity_linking erschlossen
- [ ] `generated_by: "entity_linking"` für erschlossene Verortungen

### B6. Output
- [ ] Alle extrahierten Events ins Schema schreiben
- [ ] `validate.py` läuft automatisch nach jedem Dokument
- [ ] Bei Validierungsfehler: Dokument in Fehler-Queue, nicht in DB

---

## Phase C: Pipeline testen
*Koppermann ist der Testfall, nicht das Ziel.*

### C1. Koppermann durch Pipeline jagen
- [x] Koppermann-Daten manuell ins Schema migriert (Referenzinstanz)
- [ ] Dieselben Dokumente (WASt-Karten, Auskunftsschreiben) durch B1–B6 jagen
- [ ] Automatisch extrahiertes Ergebnis vs. manuell erstellte Referenz vergleichen

### C2. Soll-Ergebnis prüfen
- [x] `resolve_location("person_koppermann_hj_1917", "1943-08-28")` → belegt, cert=5, lat≠None ✓
- [x] `resolve_location("person_koppermann_hj_1917", "1943-11")` → belegt, cert=5 ✓
      (Marburg korrekt — November 1943 war er im Reserve-Lazarett Marburg, nicht Trier)
- [x] `resolve_location("person_koppermann_hj_1917", "1945-01")` → belegt, cert=5 ✓
      (WASt Karte II hat Datum aber keinen Ort — sicherheit=belegt ist korrekt)
- [x] `resolve_location("person_koppermann_hj_1917", "1941-07")` → einheit oder unbekannt ✓
      (N.A. 20 nicht bei Tessin erfasst → strukturelle Quelllücke, kein Pipeline-Fehler)
- [x] `resolve_location("person_koppermann_hj_1917", "1940-03")` → unbekannt ✓
- [x] Cold-Run 2026-06-12: 5/5 Checks bestanden (kein manueller Eingriff)

### C3. Korrekturen
- [ ] Korrekturen gehen in Pipeline (Phase B), nie in Rohdaten
- [ ] Nach jeder Korrektur: Pipeline erneut gegen Koppermann testen
- [ ] Akzeptanzkriterium: >90% der Felder korrekt extrahiert

---

## Phase D: Karte und UI
*Präsentation. Erst sinnvoll nach A3 (Koordinaten) und C (validierte Pipeline).*

### D1. Datenbankabfragen als API
- [ ] `verorte(actor_id, zeitpunkt)` → Punkt mit Sicherheitsstufe
- [ ] `kontext(actor_id, zeitpunkt, radius_km)` → Events in der Nähe
- [ ] Beide als lokale Python-API, kein externer Server

### D2. Karte liest aus DB
- [ ] Koppermann-Karte (`koppermann_karte.html`) liest aus `familiengeschichte.db`
      statt aus statischen JSONs
- [ ] Stanford-Grenzen bleiben als statischer Layer (GeoJSON)
- [ ] Alle anderen Layer aus DB-Abfragen

### D3. Review-Interface
- [ ] Nutzer sieht Event-Liste nach Dokumentupload, kann korrigieren
- [ ] Unsichere Stellen hervorgehoben (certainty ≤ 2 → orange)
- [ ] Nicht aufgelöste Abkürzungen: Nutzer kann Bedeutung eingeben
- [ ] Diff-Ansicht: automatisch extrahiert vs. bereits bekannt

### D4. Export
- [ ] JSON-Export der extrahierten Daten pro Person
- [ ] Auto-generierter Markdown-Bericht (wie `hohenstaufen_fehler.md`)
- [ ] Quellenangaben-Liste für Fußnoten

---

## Offene Fragen / Abhängigkeiten

- **Bd. 16-x (0 Join-Events):** Andere Struktur als andere Bände?
  Manuell prüfen bevor Pipeline für restliche Bände läuft
- **Gazeteer (A3):** Beschaffung historischer Ortsnamen-Daten —
  GeoNames kostenlos aber unvollständig für Ostfront-Orte
- **Handschrift (B3):** Größtes technisches Risiko — bewusst spät,
  damit es den Rest nicht blockiert
- **Mehrsprachigkeit:** Polnische/russische Dokumente erst nach
  deutschem Kern
- **KTB-Ebene:** Explizit nicht Teil dieser Pipeline —
  separates Projekt wenn überhaupt

---

## Haltepunkte
*Jeder liefert einen funktionierenden Stand.*

| Nach | Stand |
|---|---|
| A1–A2 | Durchsuchbare Wehrmacht-Einheitsdatenbank (eigenständig wertvoll) |
| A3–A4 | Kontext-Abfragen funktionieren: wer war wo, was passierte in der Nähe |
| B1–B6 | Pipeline verarbeitet neue Dokumente automatisch |
| C | Pipeline ist validiert, Qualität bekannt |
| D | Öffentlich nutzbares Werkzeug |

---

*Schema-Version: 1.1 | Zuletzt aktualisiert: 2026-06-24*
