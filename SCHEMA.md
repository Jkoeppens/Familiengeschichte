# SCHEMA.md — Datenvertrag Familiengeschichte-Pipeline

**Lies dieses Dokument bevor du irgendetwas schreibst.**
Alle neuen Daten müssen gegen die JSON-Schema-Dateien in `schema/` valide sein.
Führe `validate.py` am Ende jeder Pipeline aus.
Bei Unklarheiten: frag. Erfinde keine neuen Felder oder Typwerte.

---

## 1. Grundprinzipien

Das Datenmodell folgt CIDOC-CRM (vereinfacht, ohne RDF/Triplestore).
**Alles dreht sich um Events.** Personen und Einheiten haben keine
statischen Eigenschaften wie "war in Frankreich" — sie nehmen an
Events teil die an Orten zu Zeitpunkten stattfinden.

Drei Kerndateien:
- `actors.json` — Personen und Militäreinheiten
- `events.json` — alle Events (Schlachten, Verwundungen, Verlegungen, Verbrechen...)
- `participations.json` — wer nimmt wie an welchem Event teil

Geodaten (KZ, Grenzen) bleiben als GeoJSON, referenzieren aber Events.

---

## 2. Datenformate — keine Ausnahmen

### Datum
```
Immer ISO 8601. Niemals Freitext.

Tag-genau:    "1943-08-28"
Monat-genau:  "1943-08"
Jahr-genau:   "1943"
Zeitspanne:   {"begin": "1943-08-28", "end": "1944-03-15", "precision": "day"}
Unbekannt:    null  — niemals "", niemals weglassen
```

Verboten: `"Aug 1943"`, `"28.8.1943"`, `"1943/08"`, `"August 1943"`

### IDs
```
Format:   {typ}_{inhalt_snake_case}
Typ-Präfixe:
  person_   → person_koppermann_hj_1917
  unit_     → unit_20_pz_gren_div
  event_    → event_koppermann_wounding_1943_08_28
  place_    → place_gorki_ilija
  source_   → source_wast_k1458_033

Regeln:
- Nur Kleinbuchstaben, Ziffern, Unterstriche
- Keine Leerzeichen, keine Bindestriche, keine Umlaute
- Immer eindeutig innerhalb des Typs
- Einmal vergeben: nie ändern
```

### Koordinaten
```json
{
  "name": "Gorki, ca. 35 km südöstlich Ilija",
  "modern_name": "Gorki, Oblast Minsk, Belarus",
  "lat": 54.02,
  "lon": 27.1,
  "precision": "lokalisiert",
  "radius_km": 5,
  "source": "WASt-Karte I"
}
```

`precision` ist immer einer von:
`"exakt"` | `"lokalisiert"` | `"stadt"` | `"region"` | `"schauplatz"`

`radius_km` ist Pflicht wenn precision != "exakt":
- lokalisiert: 1–10
- stadt: 10–30
- region: 30–150
- schauplatz: kein Punkt, kein radius_km, lat/lon = null

### Unsichere / unbekannte Werte
```
Immer explizit null setzen. Niemals Feld weglassen wenn es im Schema steht.
Niemals "" als Ersatz für null.
Niemals 0 als Ersatz für null bei Koordinaten.
```

---

## 3. Enum-Werte — nur diese, keine anderen

### `event.type`
```
Personenbezogen:
  Birth | Death | Missing | Promotion | Wounding
  Hospitalization | Discharge | Capture | PersonJoining

Einheitsbezogen:
  UnitFormation | UnitDissolution | UnitNaming
  UnitJoining | TroopMovement

Kriegsereignisse:
  Battle | Encirclement | Siege | Retreat | Surrender

Verbrechen:
  Atrocity | MassExecution | Deportation | GhettoOperation | ForcedLabor

Sonstiges:
  DocumentCreation | Unknown
```

Neuen Typ nur nach expliziter Absprache und Ergänzung dieses Dokuments.

### `event.subtype`
Freitext, optional. Präzisiert den Typ.
Beispiele: `"Granatsplitterverwundung"`, `"Relazarettierung"`, `"Vernichtungslager"`

### `participation.relation`
```
had_participant         — direkte Teilnahme (stärkste Aussage)
occurred_in_presence_of — anwesend, nicht direkt beteiligt
was_influenced_by       — betroffen von, räumlich/zeitlich getrennt
perpetrator             — Täter (nur bei Atrocity-Events)
victim                  — Opfer (nur bei Atrocity-Events)
```

### `participation.role`
```
Für Personen:   soldier | patient | commander | prisoner | victim | witness
Für Einheiten:  unit | superior | subordinate | allied | opposing
Für Orte:       location | origin | destination
```

### `source.type`
```
wast              — WASt-Zentralkarteikarte (Primärquelle)
bundesarchiv      — Bundesarchiv-Auskunftsschreiben (Primärquelle)
tessin            — Tessin, Verbände und Truppen (Sekundärquelle)
drk               — DRK-Suchdienst / Rotes Kreuz
brief             — Brief, Tagebuch, mündliche Überlieferung
ushmm             — USHMM Encyclopedia / Holocaust Geographies
stanford          — Stanford Spatial History Project
sekundaer         — Andere Sekundärliteratur
manuell           — Manuell eingetragen ohne spezifische Quelle
```

### `source.generated_by`
```
direkt          — steht explizit in der Quelle
entity_linking  — per Verknüpfungslogik erschlossen
                  (Person war in Einheit → Einheit war an Ort → Person dort)
manuell         — Nutzer hat es eingetragen oder korrigiert
```

### `source.certainty` (integer 1–5)
```
5 — Primärquelle, Ort und Datum explizit (WASt-Einzelmeldung mit Datum+Ort)
4 — Primärquelle, Datum oder Ort unscharf (Bundesarchiv-Auskunft ohne Monat)
3 — Sekundärquelle zuverlässig (Tessin, USHMM)
2 — Erschlossen (entity_linking: Einheitsstandort → Personenstandort)
1 — Unsicher (Nachkriegsrekonstruktion, mündliche Überlieferung)
```

### `actor.type`
```
Person | MilitaryUnit | Organization | Place
```

### `actor.branch` (nur für MilitaryUnit)
```
Heer | Luftwaffe | Kriegsmarine | Waffen-SS | Ordnungspolizei
Einsatzgruppe | Sicherheitsdienst | Unknown
```

### `actor.unit_type` (nur für MilitaryUnit)
```
Division | Regiment | Bataillon | Kompanie | Abteilung | Korps | Armee
Heeresgruppe | Sonderverband | Unknown
```

### `place.precision`
```
exakt       — GPS-Genauigkeit, radius_km nicht nötig
lokalisiert — aus Quellenangabe erschlossen, radius_km 1-10
stadt       — Stadtebene, radius_km 10-30
region      — Regionsebene, radius_km 30-150
schauplatz  — nur Schauplatz bekannt, lat/lon = null
```

---

## 4. Pflichtfelder pro Typ

### Actor (Person oder MilitaryUnit)
```
Pflicht:   id, type, pref_label, alt_labels, created_at
Optional:  family_name, given_name, birth_date, birth_place (Person)
           abbr, branch, unit_type, heimatgarnison, wehrkreis (MilitaryUnit)
           parent_unit_id, same_as, notes
```

`alt_labels` ist immer ein Array, auch wenn leer: `[]`

### Event
```
Pflicht:   id, type, label, time_span, source, created_at
Optional:  subtype, place, description, atrocity_details, medical_details
```

`time_span` ist immer ein Objekt: `{begin, end, precision}` — nie ein String.
`source` ist immer ein Objekt, nie ein String.

### Participation
```
Pflicht:   event_id, actor_id, relation, role
Optional:  note, certainty_override
```

`certainty_override` nur setzen wenn die Beteiligung unsicherer ist
als die Event-Quelle es nahelegt.

### Source (eingebettet in Event)
```
Pflicht:   type, certainty, generated_by
Optional:  reference, url, page, accessed_date, note
```

---

## 5. Verbotene Muster

```
❌  Koordinaten als Array:           [54.02, 27.1]
✓   Koordinaten als Objekt:          {"lat": 54.02, "lon": 27.1, ...}

❌  Datum als String ohne Format:    "August 1943"
✓   Datum ISO:                       "1943-08"

❌  Feld weglassen wenn unbekannt:   (kein alt_labels Feld)
✓   Explizit null oder leer:         "alt_labels": []

❌  Freitext in Enum-Feldern:        "type": "Lazarettaufnahme"
✓   Korrekter Enum-Wert:             "type": "Hospitalization"

❌  Neue Typen erfinden ohne Absprache
✓   Fragen und dieses Dokument aktualisieren

❌  ID mit Bindestrich:              "unit-20-pz-gren-div"
✓   ID mit Unterstrich:              "unit_20_pz_gren_div"

❌  certainty als String:            "certainty": "hoch"
✓   certainty als Integer:           "certainty": 4

❌  Mehrere Quellen in einem Event ohne Priorisierung
✓   Beste Quelle in source, Alternativen in source_alternatives[]
```

---

## 6. Versionierung und Änderungen

- Schema-Version: `1.0`
- Jede Änderung an Enum-Werten oder Pflichtfeldern:
  1. Dieses Dokument aktualisieren
  2. JSON-Schema-Dateien aktualisieren
  3. `validate.py` laufen lassen
  4. Git-Commit mit Nachricht "schema: [was geändert]"

- Feldnamen nie umbenennen ohne Migration aller bestehenden Daten
- IDs nie ändern nach erstem Commit

---

## 7. Referenzinstanz: Koppermann

Die Koppermann-Daten sind der Goldstandard.
Jede Pipeline-Änderung muss diese Abfragen korrekt beantworten:

```python
verorte("person_koppermann_hj_1917", "1943-08-28")
# → Gorki, lat=54.02, lon=27.1, certainty=5, source.type="wast"

verorte("person_koppermann_hj_1917", "1943-11")
# → Trier, lat=49.75, lon=6.64, certainty=5, source.type="wast"

verorte("person_koppermann_hj_1917", "1941-07")
# → Minsk-Raum, certainty=2, generated_by="entity_linking"

kontext("person_koppermann_hj_1917", "1941-07", radius_km=200)
# → enthält event_minsk_ghetto_1941, relation="occurred_in_presence_of"
```

---

*Zuletzt aktualisiert: 2026-06-11 | Schema-Version: 1.0*
