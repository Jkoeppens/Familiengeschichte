# Pipeline-Baseline: Tessin Bd. 4

Referenzwerte aus `tessin_bd4_final.json` (Stand 2026-06-10).
Alle weiteren Bände werden gegen diese Messlatte geprüft.

---

## Grundstatistik

| Kennzahl | Wert |
|---|---|
| Einträge gesamt | 1020 |
| davon mit Unterstellungstabelle | 76 |
| Zeilen (Unterstellungseinträge) | 1143 |
| LLM-geparst | 670 (58,6 %) |
| Regex-korrigiert (ohne LLM) | 54 (4,7 %) |
| Unverändert übernommen | 419 (36,7 %) |
| LLM-Fehler | 0 |

---

## Feldbesetzungsrate

| Feld | Belegt | Rate | Kommentar |
|---|---|---|---|
| `theater` | 1046 / 1143 | **91,5 %** | Zuverlässigste Angabe |
| `armee` | 917 / 1143 | **80,2 %** | |
| `korps` | 889 / 1143 | **77,8 %** | z.Vfg./inAufst. = leer, korrekt |
| `ort` | 558 / 1143 | **48,8 %** | nach Blacklist-Bereinigung |
| `hgr` | 467 / 1143 | **40,9 %** | strukturell begrenzt (s. u.) |

---

## Goldstandard: 20. Infanterie-Division (mot.) / 20. Pz.Gren.Div.

39 Monatseinträge, Sept. 1939 – April 1945.

| Feld | Treffer | Quote |
|---|---|---|
| `korps` | 39 / 39 | **100 %** |
| `theater` | 38 / 39 | **97 %** |
| `armee` | 31 / 39 | **79 %** |
| `hgr` | 8 / 39 | **21 %** |

---

## Bekannte Restprobleme (strukturell, kein Bug)

**hgr 60 % leer — erwartet und korrekt:**
Tessin nennt die Heeresgruppe nur, wenn sie explizit im Text erscheint.
Bei Westfront-/Besatzungsperioden (1940–41) und frühen Ostfront-Phasen
fehlt die Hgr.-Angabe im Quelltext.

| Schauplatz | hgr-Besetzung |
|---|---|
| `theater = Osten` | 206 / 323 = 64 % |
| `theater = Westen / Heimat` | 74 / 236 = 31 % |

**XI.SS-Typ unberührt:**
`fix_roman_ocr()` erkennt `.SS`, `.Lw`, `.Pz`-Suffixe korrekt als Nicht-Röm.-Zeichen
und lässt `XI.SS`, `I.Lw` usw. unverändert. Diese Tokens sind gültig.

**Weitere offene Einzelfälle:**
- `korps = X.XI` bereits → `XXI` behoben (roman_ocr Fix)
- `korps = GD` (Großdeutschland) bleibt erhalten — kein OCR-Fehler
- Doppelte Monatsangaben in `monat`-Feld (`Jan./Mai`) sind Tessin-Original, kein Fehler

---

## Schwellenwerte für neue Bände

Ein neuer Band **besteht die Qualitätsprüfung**, wenn:

| Metrik | Mindest-Schwelle |
|---|---|
| `theater`-Besetzung | ≥ 85 % |
| `korps`-Besetzung | ≥ 70 % |
| `armee`-Besetzung | ≥ 70 % |
| LLM-Fehlerrate | ≤ 5 % |
| Goldstandard `korps` (wenn 20. Div. im Band) | 100 % |

Liegt ein Band **deutlich unter** diesen Werten → anderes OCR-Layout oder
abweichende Tessin-Struktur; Pipeline-Anpassung nötig bevor der Band eingeflossen ist.

---

## Reproduzierbarkeit

```bash
# Vollständiger Lauf (LLM erforderlich, ~30 min):
python3 normalize_pipeline.py --input tessin_bd4.json

# Nur Postprocessing (kein LLM, Sekunden):
python3 normalize_pipeline.py --input tessin_bd4.json --postprocess --finalize

# Qualitätsprüfung neuer Band (Beispiel Bd. 1):
python3 normalize_pipeline.py --input tessin_bd1.json
python3 normalize_pipeline.py --input tessin_bd1.json --postprocess --finalize
```
