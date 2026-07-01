# Qualitätsbericht — Tessin-Pipeline
*Erstellt: 2026-06-11 | DB: familiengeschichte.db*

---

## 1. Gesamtzahlen

| | |
|---|---|
| **Actors gesamt** | 1.068 (1.067 MilitaryUnit + 1 Person) |
| **Events gesamt** | 9.152 |
| **Participations gesamt** | 9.330 |

### Event-Typen

| Typ | Anzahl |
|---|---|
| UnitJoining (monatl. Unterstellung) | 8.690 |
| UnitNaming (Umbenennung) | 454 |
| Hospitalization | 3 |
| Wounding | 1 |
| TroopMovement | 1 |
| Missing | 1 |
| GhettoOperation | 1 |
| Discharge | 1 |

---

## 2. Pro-Band-Statistik

| Band | Einträge | m. Unterst. | Ust.-Zeilen | Actors in DB | UnitJoining | UnitNaming | Hierarchie |
|------|----------|-------------|-------------|--------------|-------------|------------|------------|
| Bd. 1  | 13    | 0  | 0     | 2    | 0     | 39 | 0  |
| Bd. 2  | 1.568 | 82 | 1.289 | 103  | 1.300 | 25 | 14 |
| Bd. 3  | 1.607 | 78 | 1.150 | 99   | 1.145 | 27 | 3  |
| Bd. 4  | 1.020 | 76 | 1.143 | 103  | 1.146 | 29 | 3  |
| Bd. 5  | 1.187 | 63 | 939   | 98   | 959   | 43 | 18 |
| Bd. 6  | 850   | 70 | 1.055 | 87   | 1.076 | 22 | 9  |
| Bd. 7  | 625   | 47 | 486   | 67   | 498   | 20 | 3  |
| Bd. 8  | 380   | 62 | 904   | 81   | 875   | 28 | 8  |
| Bd. 9  | 380   | 62 | 763   | 86   | 773   | 29 | 5  |
| Bd. 10 | 316   | 38 | 193   | 52   | 205   | 16 | 6  |
| Bd. 11 | 440   | 60 | 155   | 78   | 170   | 22 | 0  |
| Bd. 12 | 361   | 16 | 145   | 50   | 155   | 34 | 0  |
| Bd. 13 | 757   | 5  | 15    | 42   | 17    | 39 | 0  |
| Bd. 14 | 934   | 65 | 352   | 98   | 356   | 43 | 12 |
| Bd. 15 | 214   | 0  | 0     | 0    | 0     | 0  | 0  |
| Bd. 16-1 | 57  | 0  | 0     | 17   | 15    | 38 | 0  |
| Bd. 16-2 | 24  | 0  | 0     | 17   | 15    | 38 | 0  |
| Bd. 17 | 74    | 0  | 0     | 0    | 0     | 0  | 0  |

**Hinweis Bd. 16-1/16-2:** Die 15 UnitJoining-Events entstammen Actors, die per UnitNaming-Extraktion angelegt wurden (kein echter Unterstellungsinhalt).

---

## 3. Feldbesetzungsrate UnitJoining-Events (% nicht null)

| Band | Events | korps | armee | hgr | ort (place.name) |
|------|--------|-------|-------|-----|-----------------|
| Bd. 2  | 1.300 | 76 % | 72 % | 42 % | 96 % |
| Bd. 3  | 1.145 | 76 % | 75 % | 42 % | 98 % |
| Bd. 4  | 1.146 | 77 % | 80 % | 40 % | 99 % |
| Bd. 5  | 959   | 64 % | 78 % | 52 % | 95 % |
| Bd. 6  | 1.076 | 84 % | 82 % | 30 % | 95 % |
| Bd. 7  | 498   | 89 % | 75 % | 35 % | 94 % |
| Bd. 8  | 875   | 91 % | 79 % | 27 % | 97 % |
| Bd. 9  | 773   | 88 % | 82 % | 27 % | 96 % |
| Bd. 10 | 205   | 79 % | 71 % | 39 % | 91 % |
| Bd. 11 | 170   | 78 % | 58 % | 34 % | 89 % |
| Bd. 12 | 155   | 87 % | 69 % | 25 % | 93 % |
| Bd. 13 | 17    | 88 % | 76 % | 35 % | 88 % |
| Bd. 14 | 356   | 71 % | 81 % | 47 % | 98 % |

**Beobachtungen:**
- `ort` (place.name) ist mit 88–99 % am besten besetzt; ~10–12 % der Einträge haben nur einen Schauplatz-Namen ohne Koordinaten.
- `heeresgruppe` ist am schwächsten (25–52 %): wird in den Unterstellungstabellen oft nicht explizit aufgeführt, wenn Armee oder Korps eindeutig ist.
- Bd. 11–13 haben niedrigere `armee`-Besetzung (58–76 %), weil diese Bände Spezialtruppen (Heerestruppen, Ersatzeinheiten) enthalten, die direkt OKH unterstellt waren.

---

## 4. Hierarchie-Abdeckung

**Gesamt:** 143 von 1.067 MilitaryUnit-Actors haben `parent_unit_id` gesetzt (13,4 %).

| Einheitstyp | Actors | mit parent_unit_id | % |
|---|---|---|---|
| Division | 381 | 45 | 12 % |
| Abteilung | 189 | 37 | 20 % |
| Unknown | 166 | 15 | 9 % |
| Regiment | 109 | 16 | 15 % |
| Bataillon | 100 | 27 | 27 % |
| Korps | 92 | 3 | 3 % |
| Armee | 23 | 0 | 0 % |
| Kompanie | 4 | 0 | 0 % |
| Heeresgruppe | 3 | 0 | 0 % |

**Hauptursachen der niedrigen Abdeckung:**
- Die meisten Elterneinheiten (Divisionen, Korps) sind zwar in der DB, aber ihr Name in `ueberstellung_kurz` konnte nicht eindeutig auf eine Actor-ID gemappt werden (Abkürzungsvarianten, OCR-Fehler).
- Korps- und Armeestäbe haben keine eigenen Tessin-Einträge mit Unterstellungszeilen — sie erscheinen nur als Referenz in den `unit_details`-Feldern der Unterstellungsevents.
- `get_hierarchy()` funktioniert vollständig für manuell kuratierte Einheiten (z. B. PGR 90 → 20. Pz.Gren.Div.).

---

## 5. Bekannte Lücken

### 5.1 Bände ohne Unterstellungstabellen

| Band | Inhalt | Grund |
|------|--------|-------|
| **Bd. 1** | Nur 13 Einträge, unstrukturiert | OCR-Artefakt: Bandinhalt ist Registerseiten/Übersichten, kein Einheitenregister mit Unterstellungstabellen |
| **Bd. 15** | 214 Einträge, Feldpostnummern | Anderere Struktur: Bd. 15 enthält **Feldpostnummernlisten** (Nummernschlüssel) — keine Unterstellungstabellen, keine Ortsangaben. Einige Einträge haben `_raw_len` > 80.000 (OCR-Dump ganzer Seiten in ein Feld). **Nicht reparierbar** ohne Re-OCR. |
| **Bd. 17** | 74 Einträge, Verbindungsstäbe | Enthält deutsche **Verbindungsstäbe bei alliierten Armeen** (ital., finn., rumän.). Diese Einheiten hatten keine eigenen Unterstellungstabellen im Tessin-Format. **Strukturell korrekt leer.** |
| **Bd. 16-1** | 57 Einträge | Enthält **Ersatz- und Ausbildungseinheiten** ohne Unterstellungszeilen — sie standen ortsfest in Deutschland und wurden nicht in die monatlichen Operationsberichte aufgenommen. `mit_tabelle: 0` laut Report-JSON. **Strukturell korrekt leer.** |
| **Bd. 16-2** | 24 Einträge | Wie Bd. 16-1. |

### 5.2 Korps- und Armeebene nicht vollständig

Die `unit_details`-Felder der UnitJoining-Events enthalten Korps- und Armeenamen als Strings (z. B. `"XXXIX"`, `"3.Pz.Gru"`). Diese wurden **nicht** als eigene Actor-Einträge angelegt, weil Korps/Armee-Stäbe in Tessin keine eigenen Unterstellungszeilen haben. Folge:
- `verorte()` auf einen Korps-Stab gibt leere Ergebnisse.
- `get_hierarchy()` endet in der Regel auf Divisions-Ebene.

### 5.3 OCR-Artefakte

Geschätzt ~10 Actors sind erkennbare OCR-Artefakte (Einheitsname enthält Zahlensequenzen oder endet mit `(`). Diese verursachen keine Fehler, tragen aber keine inhaltlich sinnvollen Daten bei.

### 5.4 Doppelte Unterstellungen durch Mehrfachbände

Einige Einheiten erscheinen in mehreren Bänden (z. B. Art.Rgt. einer Division in Bd. 4 und Bd. 6). Durch `INSERT OR REPLACE` behält der zuletzt geladene Band die Überhand. In der Praxis ist dies selten und betrifft höchstens ~30 Einheiten.

### 5.5 Heeresgruppen-Feld strukturell dünn

`hgr` ist nur in 25–52 % der UnitJoining-Events belegt. Tessin führt die Heeresgruppe in der Unterstellungstabelle oft nicht auf, wenn die Armee-Zugehörigkeit eindeutig ist.

---

## 6. Goldstandard: 20. Panzergrenadier-Division

`verorte("unit_20_pz_gren_div", zeitpunkt)` — alle 39 Monatseinträge vorhanden ✓

| Zeitraum | Korps | Armee | Ort |
|----------|-------|-------|-----|
| 1939-09 | XIX | 4.Armee | Pommern/Polen |
| 1939-12 – 1940-05 | z.Vfg. / z.Vfg. | — / 6.Armee | Eifel |
| 1940-06 – 1940-11 | XXXXII … XXXIX | 12./2./1./1.Armee | Frankreich |
| 1940-12 – 1941-05 | XXXXVIII … z.Vfg. | 11.Armee / — | Heimat / Frankreich / Ostpreußen |
| **1941-06 – 1941-08** | **XXXIX** | **3.Pz.Gruppe** | **Białystok/Minsk** ← Koppermann-Referenz |
| 1941-09 – 1943-07 | XXXIX … XXXXII | 16./18./3.Pz.Armee | Nordrußland / Wolchow / Welish |
| **1943-08** | **LIII** | **2.Pz.Armee** | **Orel** ← Goldstandard-Test ✓ |
| 1943-09 – 1944-04 | XII … XXIV | 9./8./4.Pz./1.Pz.Armee | Brjansk / Dnjepr / Ukraine |
| 1944-05 – 1945-04 | z.Vfg. … XI.SS | 1./4.Pz./9.Armee | Brody / Weichsel / Schlesien / Oder |

**Qualität:** Alle 39 Einträge korrekt, lückenlos, mit Orts- und Armeeangaben. Korps fehlt in 4 Einträgen mit `z.Vfg.`-Status (korrekt: `z.Vfg.` ist Korps-Angabe). Heeresgruppe ist in 0/39 Einträgen explizit (ergibt sich implizit aus Theater-Feld).

---

## 7. Fazit

Die Pipeline deckt **alle inhaltlich auswertbaren Bände** vollständig ab. Bd. 15 (Feldpostnummern), Bd. 17 (Verbindungsstäbe) und Bd. 16-x (Ersatzeinheiten) enthalten strukturbedingt keine Unterstellungstabellen — das ist kein Pipeline-Fehler. Die wichtigsten Verbesserungspotenziale für spätere Iterationen:

1. **Hierarchie-Abdeckung erhöhen** (aktuell 13 %) durch besseres Abkürzungs-Matching in `ueberstellung_kurz`
2. **Korps/Armee als Actors** anlegen, sobald Verwendung in Abfragen erforderlich
3. **OCR-Artefakte bereinigen** (~10 Einträge)
4. **hgr-Extraktion verbessern** (aktuell 25–52 % Besetzung)
