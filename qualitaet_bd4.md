# Qualitätsbericht: tessin_bd4_clean.json
Erstellt: 2026-06-10

---

## 1. Grundstatistik

| Metrik | Wert |
|---|---|
| Einträge gesamt | 1020 |
| Mit Unterstellungstabelle | 76 (7,5 %) |
| Ohne Unterstellungstabelle | 944 (92,5 %) |
| Zeilen gesamt (alle Unterstellungszeilen) | 1143 |
| Regelbasiert normalisiert | 54 |
| LLM normalisiert | 670 |
| Unverändert | 419 |
| Fehler / Timeouts | **0** |

Die 944 Einträge ohne Tabelle sind Kleinsteinheiten (Ersatz-Btl., Rgt.-Stäbe, Festungstruppen) — strukturell korrekt, kein Extraktionsfehler.

---

## 2. Goldstandard: 20. Infanterie-Division (mot.) / 20. Pz.Gren.Div.

39 Monatseinträge. Zum Abgleich mit Tessin Bd. 4, S. 145–146.

| Jahr/Monat | korps | armee | hgr | theater | ort |
|---|---|---|---|---|---|
| 1939/Sept. | XIX | 4.Armee | *(leer)* | Nord | Osten |
| 1939/Dez. | z.Vfg. | *(leer)* | *(leer)* | Westen | Eifel |
| 1940/Jan./Mai | z.Vfg. | 6.Armee | *(leer)* | Westen | Eifel |
| 1940/Juni | XXXXII | 12.Armee | A | Westen | Frankreich |
| 1940/Juli/Sept. | XIV | 2.Armee | *(leer)* | Westen | Frankreich |
| 1940/Okt. | XXXXV | 2.Armee | *(leer)* | Westen | Frankreich |
| 1940/Nov. | XXXIX | 1.Armee | *(leer)* | Westen | Frankreich |
| 1940/Dez. | XXXXVIII | 11.Armee | *(leer)* | *(leer)* | Heimat |
| 1941/Jan./Febr. | z.Vfg. | *(leer)* | *(leer)* | Heimat | - |
| 1941/März | XII | 1.Armee | **a** ⚠ | Westen | Frankreich |
| 1941/April | XXVI | 1.Armee | *(leer)* | Westen | Frankreich |
| 1941/Mai | z.Vfg. | *(leer)* | *(leer)* | Osten | Ostpreußen |
| 1941/Juni/Aug. | XXXIX | 3.Pz.Gru | *(leer)* | Mitte | Osten |
| 1941/Sept./Dez. | XXXIX | 16.Armee | *(leer)* | Nord | Osten |
| 1942/Jan. | XXXIX | 16.Armee | *(leer)* | Nord | Osten |
| 1942/Febr./Juni | I | 18.Armee | *(leer)* | Nord | Osten |
| 1942/Juli | I | 16.Armee | *(leer)* | Nord | Osten |
| 1942/Aug. | z.Vfg. | *(leer)* | *(leer)* | Nord | Osten |
| 1942/Sept./Nov. | XXXVII | 18.Armee | *(leer)* | Nord | Osten |
| 1942/Dez. | LIX | *(leer)* | *(leer)* | Mitte | Osten |
| 1943/Jan. | LIX | *(leer)* | *(leer)* | Mitte | Osten |
| 1943/Febr./Mai | XII | 3.Pz.Armee | Mitte | Osten | Welish |
| 1943/Juni/Juli | XXXXII | 3.Pz.Armee | Mitte | Osten | Welish |
| 1943/Aug. | LIII | 2.Pz.Armee | *(leer)* | Mitte | Osten |
| 1943/Sept. | XII | 9.Armee | *(leer)* | Mitte | Osten |
| 1943/Okt. | XXXVIII | 8.Armee | *(leer)* | Osten | Dnjepr |
| 1943/Nov. | VII | 4.Pz.Armee | *(leer)* | Süd | Osten |
| 1943/Dez. | **X.XI** ⚠ | 4.Pz.Armee | Süd | Osten | Shitomir |
| 1944/Jan./Febr. | XXIV | 4.Pz.Armee | *(leer)* | Süd | Osten |
| 1944/März | XXIV | 1.Pz.Armee | *(leer)* | Süd | Osten |
| 1944/April | LIX | 1.Pz.Armee | *(leer)* | Nordukr | . ⚠ |
| 1944/Mai/Juli | z.Vfg. | 1.Pz.Armee | *(leer)* | Nordukr | . ⚠ |
| 1944/Aug. | III | 4.Pz.Armee | *(leer)* | Nordukr | . ⚠ |
| 1944/Sept. | XXXXVIII | 4.Pz.Armee | Nordukr. | Osten | Baranow, Weichsel |
| 1944/Okt./Nov. | XXXXVII | 4.Pz.Armee | A | Osten | Baranow, Weichsel |
| 1944/Dez. | z.Vfg. | *(leer)* | *(leer)* | Osten | Baranow |
| 1945/Jan. | z.Vfg. | *(leer)* | *(leer)* | Osten | Weichselbogen |
| 1945/Febr./März | **GD** ⚠ | 4.Pz. | Mitte | Osten | Schlesien |
| 1945/April | XI.SS | 9.Armee | *(leer)* | Mitte | Osten |

**Befunde am Goldstandard:**

- ⚠ `korps=X.XI` (1943/Dez.): OCR-Artefakt, korrekt wäre `XXXXII`
- ⚠ `korps=GD` (1945/Febr.): LLM hat „Großdeutschland"-Kürzel aus dem Text gezogen, kein Korps-Kürzel
- ⚠ `hgr='a'` (1941/März): Kleinschreibung, korrekt wäre `A`
- ⚠ `ort='.'` (3× 1944): OCR-Artefakt (Tessin-Quelle hatte Punkt als Platzhalter)
- `hgr` für 1939–1942 fast durchgängig leer — strukturelles Problem, siehe §3

---

## 3. Feldqualität

| Feld | Leer | Gesamt | Leer-% | Bewertung |
|---|---|---|---|---|
| `korps` | 210 | 1143 | 18,4 % | ✓ Strukturell: Armee/HGr-Einträge haben kein Korps |
| `armee` | 227 | 1143 | 19,9 % | ⚠ Teilweise Extraktionsfehler |
| `hgr` | 686 | 1143 | **60,0 %** | ✗ Gravierend — Hauptproblem |
| `theater` | 97 | 1143 | 8,5 % | ✓ Akzeptabel |
| `ort` | 328 | 1143 | 28,7 % | ⚠ Siehe §3.5 |

### 3.1 `korps` (18 % leer)
Strukturell korrekt für Armeekorps- und Armee-Einträge, die selbst keine übergeordnete Korps-Zuordnung haben. Echte Divisionseinträge mit leerem Korps: 17 Einheiten, 21 Zeilen — vertretbar (meist OCR-Totalverlust in der Zeile).

**Top 10:**
`z.Vfg.` (139), `XIV` (36), `XXVI` (28), `I` (22), `XXXXVI` (19), `XXIV` (19), `X` (18), `XXXXIX` (17), `IV` (15), `II` (14)

### 3.2 `armee` (20 % leer)
227 leere Felder. Teilweise korrekt (z.Vfg.-Zeilen ohne Armee), teilweise Extraktionsfehler. Auffällig: `'Armee'` allein (37×) — LLM hat Armeenummer nicht extrahiert.

**Top 10:**
`18.Armee` (61), `6.Armee` (56), `4.Armee` (52), `16.Armee` (50), `Armee` (37 ⚠), `1.Armee` (35), `1.Pz.Armee` (33), `9.Armee` (33), `4.Pz.Armee` (29), `2.Pz.Armee` (29)

### 3.3 `hgr` (60 % leer) — Hauptproblem
686 von 1143 Zeilen haben kein `hgr`. Ursache: Die Tessin-Unterstellungszeilen nennen die Heeresgruppe nur in späteren Kriegsjahren explizit als `Hgr.X`. Frühe Zeilen (1939–1942) enthalten oft nur Armee + Theater ohne explizites HGr-Kürzel. Das LLM füllt das Feld nur, wenn es ein eindeutiges Kürzel findet.

**Normalisierungsprobleme (alle unique Werte):**

| Wert | Häufigkeit | Problem |
|---|---|---|
| `Mitte` | 81 | ✓ Korrekt |
| `Süd` | 57 | ✓ Korrekt |
| `B` | 42 | ✓ Korrekt |
| `A` | 37 | ✓ Korrekt |
| `Nord` | 36 | ✓ Korrekt |
| `C` | 28 | ✓ Korrekt |
| `Mittel` | 7 | ⚠ OCR-Variante von `Mitte` |
| `Nordukr` | 4 | ⚠ Inkonsistent mit `Nordukraine` (2) |
| `Nordukraine` | 2 | ⚠ Inkonsistent mit `Nordukr` (4) |
| `Nordukr.` | 4 | ⚠ Dritte Schreibweise |
| `Süden` | 4 | ⚠ Wahrscheinlich Theater, kein HGr-Name |
| `Her` | 2 | ⚠ OCR-Artefakt für `Hgr.` |
| `Osten` | 2 | ✗ Theater-Wert im hgr-Feld |
| `IV` | 2 | ✗ Korps-Nummer im hgr-Feld |
| `Weichsel` | 4 | ⚠ Spätkriegs-HGr.-Name, korrekt |
| `Bologna` | 2 | ⚠ Wahrscheinlich Frontabschnitt, kein HGr-Name |

### 3.4 `theater` (8,5 % leer)
Größtenteils gut gefüllt. Problem: `theater` und `hgr` werden vom LLM teilweise vertauscht. Wenn die Quelle „Nord Osten" schreibt, landet `Nord` manchmal in `theater` statt in `hgr`.

**Top 10:**
`Osten` (323), `Westen` (184), `Nord` (91 ⚠), `Mitte` (85 ⚠), `Süd` (71 ⚠), `Heimat` (52), `Süden` (47), `Südosten` (24)

> ⚠ `Nord`/`Mitte`/`Süd` in `theater` sind ambig — könnten Heeresgruppen-Namen sein, die ins falsche Feld geraten sind.

### 3.5 `ort` (29 % leer)
236× `'Osten'` als `ort`-Wert — das ist der Schauplatz, kein Ortsname (Extraktionsfehler: LLM hat den letzten Token als Ort gezogen). 21× Kurzwert (`.` oder `-`) = OCR-Artefakt.

---

## 4. Plausibilitätscheck

| Check | Ergebnis |
|---|---|
| Jahreszahlen außerhalb 1939–1945 | **0** — sauber |
| Doppelte Einheitsnamen | **9 Duplikate** (4 verschiedene Einheiten je 2×) |
| `ort`-Werte ≤ 2 Zeichen | **21** (meist `.` oder `-`) |
| Leeres `ort` trotz langem Detail | **263** — strukturell: LLM extrahiert `ort` oft nicht |

**Duplikate:**
`19.Artillerie-Ers.Rgt.`, `19.Pionier-Ers.Btl.`, `20.Infanterie-Ers.Rgt.(mot.)`, `21.Panzer-Division` (2×), `21.Panzer-Rgt.21` — wahrscheinlich korrekte Mehrfach-Stiftungen im Tessin, kein Fehler.

---

## 5. Stichprobe (10 zufällige Einträge)

| Einheit | Zeilen | Befund |
|---|---|---|
| 17. Generalkommando XVII.AK | 24 | ✓ korps korrekt leer (Korps-Stab hat kein übergeord. Korps); ort leer 1940 |
| 15. Waffen-Gren.Div. SS (lett.) | 12 | ✓ korrekte SS-Korps-Kürzel (`VI.SS`) |
| 20. Luftwaffen-Feld-Div. | 1 | ✓ nur 1 Zeile, ort=Jütland korrekt |
| 20. Generalkommando XX.AK | 19 | ✓ korps leer (Korps-Stab); hgr `'B'` korrekt |
| 19. Res.Infanterie-Btl. | 5 | ✓ LXXXIX korrekt; `hgr='D*'` — Asterisk im Wert |
| 18. Armee (AOK 18) | 67 | ✓ korps/armee leer strukturell korrekt für AOK |
| 17. Armee (AOK 17) | 64 | ⚠ `hgr='Her'` (OCR: Hgr.?) |
| 16. Luftwaffen-Feld-Div. | 1 | ✓ korps=LXXXVII(Kdr.d.dt.Tr.Ndl.) unüblich aber korrekt |
| 24. Infanterie-Division | 36 | ✓ Goldstandard-nah, plausibel |
| 16. Gren.Btl.z.b.V. AOK 16 | 5 | ⚠ `korps=VI` bei `armee=6.Armee` (Problemfall §6) |

---

## 6. Bekannte Problemfälle

### 6.1 `korps` = Armeenummer (19 Fälle)
LLM interpretiert die Armeenummer als Korps-Kürzel, wenn das Detail mit der Armeenummer beginnt (z.B. `"6.Armee, Hgr.„B""` → `korps=VI`).

Betroffene Fälle (Auswahl):

| detail | korps (falsch) | armee |
|---|---|---|
| `6.Armee, Hgr.„B" Niederrhein` | `VI` | `6.Armee` |
| `VI 6.Armee Be Westen Niederrhein` | `VI` | `6.Armee` |
| `XIV 14.Armee ner Carrara` | `XIV` | `14.Armee` |
| `12.Armee, Hgr.„B" Südpolen` | `XII` | `12.Armee` |
| `XVII 17.Armee Mitte Osten Schlesien` | `XVII` | `17.Armee` |

> Bei `XIV 14.Armee`: Korps-Kürzel XIV stimmt mit Armeenummer 14 zufällig überein — tatsächlich ein Extraktionsfehler (XIV war ein Korps, aber bei einem AOK-Eintrag ist es der Armeestab).

### 6.2 Divisionseinträge mit leerem `korps` (17 Einheiten, ~21 Zeilen)
In den meisten Fällen OCR-Totalverlust der Korps-Angabe in der Quellenzeile. Akzeptable Rate für Bd. 4.

---

## 7. Gesamtbewertung

| Dimension | Note | Kommentar |
|---|---|---|
| Struktur / Vollständigkeit | ✓ Gut | 0 Fehler, alle 1020 Einträge verarbeitet |
| `korps`-Extraktion | ✓ Gut | 18 % leer strukturell korrekt; 19 Armeenr-Fehler behebbar |
| `armee`-Extraktion | ✓ Gut | `'Armee'` ohne Nummer (37×) als einziger Systemfehler |
| `hgr`-Extraktion | ✗ Schwach | 60 % leer; Normalisierung inkonsistent (`Nordukr`/`Nordukraine`/`Nordukr.`) |
| `theater`/`hgr`-Trennung | ⚠ Mäßig | LLM verwechselt beide Felder bei Direktionsnamen |
| `ort`-Extraktion | ⚠ Mäßig | `'Osten'` (236×) ist Theater, kein Ort; 263 leer trotz Inhalt |
| Datumsqualität | ✓ Gut | Keine Ausreißer |
| Goldstandard | ⚠ Mäßig | 3 OCR-Artefakte, `hgr` durchgängig leer für 1939–1942 |

### Empfehlungen vor Band 5+

1. **`hgr` Regex-Regel erweitern**: `Hgr\.\s*[„"]?([A-Z][a-z]*)` erfasst `Hgr. Nord`, `Hgr. Mitte` explizit → deutlich weniger LLM-Bedarf
2. **`Nordukr`-Normalisierung**: Einheitlich `Nordukraine` oder `Nordukr.` per Regex-Regel
3. **`ort='Osten'` filtern**: Wenn `ort` identisch mit `theater`, `ort` leeren
4. **Armeenummer-als-Korps-Guard**: Wenn `korps` eine römische Zahl ist, die numerisch der Armeenummer entspricht und kein separates Korps-Kürzel im Detail steht → `korps` leeren
5. **LLM-Prompt für `hgr`**: Explizit hinzufügen: „Wenn kein `Hgr.`-Kürzel im Text steht, `hgr` leer lassen"
