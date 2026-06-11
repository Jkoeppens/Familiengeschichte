#!/usr/bin/env python3
"""
geocode.py — Auflösung von Ortsnamen aus den UnitJoining-Events

Hierarchie:
  1. SCHAUPLATZ-Blacklist       → precision="schauplatz", keine Koordinaten
  2. Interne _GEO_EXTENDED-DB   → kompilierte Städte/Orte (Vorrang vor JSON-Dateien)
  3. gazeteer_historisch.json   → historische Städtenamen mit modernen Koordinaten
  4. gazeteer_regionen.json     → Kriegsregionen als Zentroide
  5. GeoNames API               → falls GEONAMES_USER gesetzt
  6. nicht_aufgeloest.json      → ungelöste Namen loggen

Ergebnis: gazeteer_cache.json (alle bisherigen Auflösungen)
"""

import json
import os
import re
import sqlite3
import urllib.request
import urllib.parse
from pathlib import Path

DB_PATH      = Path(__file__).parent / "familiengeschichte.db"
CACHE_FILE   = Path(__file__).parent / "gazeteer_cache.json"
HISTORISCH   = Path(__file__).parent / "gazeteer_historisch.json"
REGIONEN     = Path(__file__).parent / "gazeteer_regionen.json"
UNRESOLVED   = Path(__file__).parent / "nicht_aufgeloest.json"

GEONAMES_USER = os.environ.get("GEONAMES_USER", "")

# ─── Blacklist: vage Schauplatz-Angaben ohne verwertbare Koordinaten ──────────

SCHAUPLATZ: set[str] = {
    # Generelle Frontbezeichnungen (zu vage für Koordinaten)
    "Osten", "Westen", "Ostfront", "Westfront", "Südostfront",
    "SüdOsten", "MitteOsten", "AOsten", "COsten", "NOsten",
    "Nord-", "Süd-", "Ost-", "West-",
    # Rußland-Varianten ohne Zentroid (wird über gazeteer_regionen abgedeckt)
    "Rußland", "Russland",
    # Heimat/Org-Status
    "Heimat", "Heimat-", "Heimat_", "Reichsgebiet", "Reich",
    "OKH-Reserve", "OKH", "z.Vfg.", "Theater",
    "unbekannt", "verschiedene", "Diverse",
    # Küsten/Gewässer ohne sinnvollen Punkt-Zentroid
    "Atlantik", "Adria", "Adria-Küste", "Mittelmeer",
    "Adria, Sangro", "Adria, Pescara", "Adria, Rimini",
    # Org-Kürzel ohne Ortsangabe
    "BdE", "Befh", "Befh.", "Befh.-", "Befehlshaber",
    "HgrMitte", "HgrNord", "HgrSüd", "HgrA", "HgrB", "HgrC",
    "HgrMitte/G", "Hgr.Mitte", "Hgr.Nord", "Hgr.Süd",
    "AOK", "OKW", "OKL", "SS-FHA",
    "Aufstellung", "inAufstellung", "inAuffrischung", "Auffrischung",
    "unverändert", "Vfg.:", "s.d.", "s.d.-",
    "Rog", "MitteRussland", "Mitte-Russland",
    "„C\"Heimat", "„A\"Osten",
    # Varia
    "#:Polen", "Skandinavien", "Afrika", "Deutschland",
    "Ostpreußen allgemein", "Frankreich allgemein",
    "Nordafrika allgemein", "Italien allgemein",
    "Schlesien allgemein", "Griechenland allgemein",
    "Prepjet", "Pripjet", "Pripjetsümpfe",
    "Kuban-Brückkopf",
    "Elsaß-Lothringen", "Ostmark",
}

# Präfix-/Suffix-Muster für blacklist-check
_SCHAUPLATZ_PREFIXES = (
    "Heimat", "Osten", "Westen", "Ostfront", "Westfront",
    "unbekannt", "AOsten", "NOsten", "COsten",
    "Arb.Stab", "Arb.", "Kampfgr.", "Gruppe", "Abt.",
    "Stab", "BdE", "Befh", "Armee", "Korps", "Div.",
    "„C\"", ",C", "C\"",
)

# ─── Interne Geo-Datenbank ────────────────────────────────────────────────────

def _geo(lat, lon, r=20, p="stadt"):
    return {"lat": lat, "lon": lon, "radius_km": r, "precision": p, "source": "internal"}

_GEO_EXTENDED: dict[str, dict] = {
    # ── Ostfront: Russland/Belarus/Ukraine ──
    "staraja russa":     _geo(57.99, 31.37),
    "staraja-russa":     _geo(57.99, 31.37),
    "starajarussa":      _geo(57.99, 31.37),
    "stararussa":        _geo(57.99, 31.37),
    "juchnow":           _geo(54.74, 35.23),
    "spass-demensk":     _geo(54.40, 34.02),
    "spas-demensk":      _geo(54.40, 34.02),
    "jelnja":            _geo(54.60, 33.18),
    "jelnia":            _geo(54.60, 33.18),
    "jelna":             _geo(54.60, 33.18),
    "orscha":            _geo(54.51, 30.42),
    "orsha":             _geo(54.51, 30.42),
    "witebsk":           _geo(55.19, 30.20),
    "vitebsk":           _geo(55.19, 30.20),
    "smolensk":          _geo(54.78, 32.04, 30),
    "rshew":             _geo(56.26, 34.33),
    "rschew":            _geo(56.26, 34.33),
    "rzhev":             _geo(56.26, 34.33),
    "kalinin":           _geo(56.86, 35.91),
    "twer":              _geo(56.86, 35.91),
    "tver":              _geo(56.86, 35.91),
    "nowgorod":          _geo(58.52, 31.27),
    "novgorod":          _geo(58.52, 31.27),
    "weliki nowgorod":   _geo(58.52, 31.27),
    "belgorod":          _geo(50.60, 36.60),
    "belgorode":         _geo(50.60, 36.60),
    "charkow":           _geo(49.99, 36.23),
    "charkiv":           _geo(49.99, 36.23),
    "charkov":           _geo(49.99, 36.23),
    "charkof":           _geo(49.99, 36.23),
    "sumy":              _geo(50.90, 34.80),
    "obojan":            _geo(51.21, 36.27),
    "obojanj":           _geo(51.21, 36.27),
    "korotscha":         _geo(50.82, 37.17),
    "achtyrka":          _geo(50.30, 34.89),
    "bobruisk":          _geo(53.14, 29.22),
    "bobrujsk":          _geo(53.14, 29.22),
    "mogilew":           _geo(53.91, 30.34),
    "mohyliw":           _geo(53.91, 30.34),
    "mogilev":           _geo(53.91, 30.34),
    "gomel":             _geo(52.44, 30.99),
    "homel":             _geo(52.44, 30.99),
    "bjelgorod":         _geo(50.60, 36.60),
    "brjansk":           _geo(53.24, 34.37),
    "bransk":            _geo(53.24, 34.37),
    "orel":              _geo(52.97, 36.07),
    "orjol":             _geo(52.97, 36.07),
    "kursk":             _geo(51.73, 36.19),
    "nikolajew":         _geo(46.97, 32.00),
    "nikolaew":          _geo(46.97, 32.00),
    "mykolaiv":          _geo(46.97, 32.00),
    "cherson":           _geo(46.64, 32.62),
    "odessa":            _geo(46.48, 30.72),
    "sewastopol":        _geo(44.61, 33.52),
    "sebastopol":        _geo(44.61, 33.52),
    "simferopol":        _geo(44.95, 34.10),
    "kertsch":           _geo(45.35, 36.47),
    "kerch":             _geo(45.35, 36.47),
    "noworossijsk":      _geo(44.72, 37.77),
    "noworossisk":       _geo(44.72, 37.77),
    "krasnodar":         _geo(45.03, 38.98),
    "taganrog":          _geo(47.24, 38.90),
    "rostow":            _geo(47.23, 39.72),
    "rostow am don":     _geo(47.23, 39.72),
    "ssalsk":            _geo(46.48, 41.54),
    "salsk":             _geo(46.48, 41.54),
    "kischinew":         _geo(47.00, 28.86),
    "chishinau":         _geo(47.00, 28.86),
    "kalinowka":         _geo(49.47, 28.53),
    "schitomir":         _geo(50.25, 28.66),
    "zhytomyr":          _geo(50.25, 28.66),
    "berdichew":         _geo(49.90, 28.60),
    "winniza":           _geo(49.23, 28.48),
    "winnizja":          _geo(49.23, 28.48),
    "proskurow":         _geo(49.41, 26.99),
    "kamenez-podolsk":   _geo(48.68, 26.58),
    "tarnopol":          _geo(49.55, 25.60),
    "rowno":             _geo(50.62, 26.25),
    "luzk":              _geo(50.74, 25.33),
    "luck":              _geo(50.74, 25.33),
    "iwano-frankiwsk":   _geo(48.92, 24.71),
    "stryj":             _geo(49.26, 23.86),
    "drohobycz":         _geo(49.35, 23.50),
    "sanok":             _geo(49.56, 22.21),
    "jaroslau":          _geo(50.01, 22.68),
    "jaroslaw":          _geo(50.01, 22.68),
    "rzeszów":           _geo(50.04, 22.00),
    "rzeszow":           _geo(50.04, 22.00),
    "kowel":             _geo(51.21, 24.71),
    "bialystok":         _geo(53.13, 23.16),
    "grodno":            _geo(53.67, 23.83),
    "baranowitsch":      _geo(53.13, 26.01),
    "baranowitschi":     _geo(53.13, 26.01),
    "pinsk":             _geo(52.11, 26.10),
    "luninets":          _geo(52.25, 26.80),
    "narew":             _geo(52.88, 22.90, 60, "region"),
    "pruth":             _geo(47.95, 27.85, 60, "region"),
    "dnjestr":           _geo(47.22, 29.43, 80, "region"),
    "bug":               _geo(51.35, 23.65, 80, "region"),
    "ilmensee":          _geo(58.20, 31.30, 60, "region"),
    "ilmen":             _geo(58.20, 31.30, 60, "region"),
    "ladogasee":         _geo(60.80, 31.50, 100, "region"),
    "leningrad":         _geo(59.95, 30.32, 30),
    "gatschina":         _geo(59.57, 30.13),
    "luga":              _geo(58.74, 29.84),
    "pskow":             _geo(57.82, 28.33),
    "narwa":             _geo(59.38, 28.18),
    "narva":             _geo(59.38, 28.18),
    "pleskau":           _geo(57.82, 28.33),
    # Belarus
    "minsk":             _geo(53.90, 27.56),
    "pinsk":             _geo(52.11, 26.10),
    # ── Westfront / Frankreich / Belgien ──
    "aachen":            _geo(50.78,  6.09),
    "trier":             _geo(49.75,  6.64),
    "saarbrücken":       _geo(49.23,  7.00),
    "saarburg":          _geo(49.60,  6.55),
    "nancy":             _geo(48.69,  6.18),
    "metz":              _geo(49.12,  6.18),
    "verdun":            _geo(49.16,  5.38),
    "reims":             _geo(49.25,  4.03),
    "aisne":             _geo(49.39,  3.50, 60, "region"),
    "soissons":          _geo(49.38,  3.32),
    "laon":              _geo(49.56,  3.62),
    "amiens":            _geo(49.89,  2.30),
    "arras":             _geo(50.29,  2.78),
    "lille":             _geo(50.63,  3.07),
    "calais":            _geo(50.95,  1.86),
    "boulogne":          _geo(50.72,  1.62),
    "dieppe":            _geo(49.92,  1.08),
    "rouen":             _geo(49.44,  1.10),
    "caen":              _geo(49.18, -0.36),
    "cherbourg":         _geo(49.63, -1.62),
    "brest":             _geo(48.39, -4.49),
    "rennes":            _geo(48.11, -1.68),
    "le mans":           _geo(48.00,  0.20),
    "paris":             _geo(48.86,  2.35, 30),
    "orleans":           _geo(47.90,  1.91),
    "orléans":           _geo(47.90,  1.91),
    "tours":             _geo(47.39,  0.69),
    "bordeaux":          _geo(44.84, -0.58),
    "bayonne":           _geo(43.49, -1.48),
    "toulouse":          _geo(43.60,  1.44),
    "montpellier":       _geo(43.61,  3.88),
    "marseille":         _geo(43.30,  5.37),
    "lyon":              _geo(45.75,  4.84),
    "grenoble":          _geo(45.19,  5.72),
    "dijon":             _geo(47.32,  5.05),
    "troyes":            _geo(48.30,  4.08),
    "chalons":           _geo(48.96,  4.36),
    "liege":             _geo(50.63,  5.57),
    "lüttich":           _geo(50.63,  5.57),
    "gent":              _geo(51.05,  3.72),
    "brügge":            _geo(51.21,  3.22),
    "namur":             _geo(50.47,  4.87),
    "mons":              _geo(50.45,  3.95),
    "sedan":             _geo(49.70,  4.95),
    "arlon":             _geo(49.68,  5.82),
    "bastogne":          _geo(50.00,  5.72),
    "luxemburg":         _geo(49.61,  6.13),
    "mainz":             _geo(50.00,  8.27),
    "frankfurt":         _geo(50.11,  8.68),
    "mannheim":          _geo(49.49,  8.47),
    "heidelberg":        _geo(49.40,  8.69),
    "freiburg":          _geo(47.99,  7.84),
    "karlsruhe":         _geo(49.00,  8.40),
    "stuttgart":         _geo(48.78,  9.18),
    "ulm":               _geo(48.40,  9.99),
    "augsburg":          _geo(48.37, 10.90),
    "münchen":           _geo(48.14, 11.58),
    "nürnberg":          _geo(49.46, 11.08),
    "würzburg":          _geo(49.80,  9.95),
    "bamberg":           _geo(49.90, 10.89),
    "erfurt":            _geo(50.98, 11.03),
    "halle":             _geo(51.48, 11.97),
    "leipzig":           _geo(51.34, 12.37),
    "dresden":           _geo(51.05, 13.74),
    "berlin":            _geo(52.52, 13.40, 30),
    "magdeburg":         _geo(52.12, 11.63),
    "braunschweig":      _geo(52.27, 10.52),
    "hannover":          _geo(52.37,  9.73),
    "bremen":            _geo(53.08,  8.80),
    "hamburg":           _geo(53.55,  9.99, 30),
    "lübeck":            _geo(53.87, 10.69),
    "kiel":              _geo(54.32, 10.13),
    "rostock":           _geo(54.09, 12.09),
    "stettin":           _geo(53.43, 14.55),
    "danzig":            _geo(54.35, 18.65),
    "königsberg":        _geo(54.71, 20.45),
    "memel":             _geo(55.71, 21.14),
    "tilsit":            _geo(55.08, 21.88),
    "insterburg":        _geo(54.63, 21.81),
    "gumbinnen":         _geo(54.65, 22.19),
    "lyck":              _geo(53.83, 22.34),
    "allenstein":        _geo(53.78, 20.49),
    "elbing":            _geo(54.16, 19.40),
    "marienburg":        _geo(54.04, 19.03),
    "dirschau":          _geo(54.08, 18.75),
    "graudenz":          _geo(53.49, 18.75),
    "thorn":             _geo(53.01, 18.60),
    "bromberg":          _geo(53.12, 18.01),
    "gnesen":            _geo(52.54, 17.60),
    "litzmannstadt":     _geo(51.76, 19.46),
    "lodz":              _geo(51.76, 19.46),
    "lodsch":            _geo(51.76, 19.46),
    "radom":             _geo(51.40, 21.15),
    "lublin":            _geo(51.25, 22.57),
    "chelm":             _geo(51.14, 23.47),
    "zamosc":            _geo(50.72, 23.25),
    "rzeszow":           _geo(50.04, 22.00),
    "krosno":            _geo(49.69, 21.77),
    "tarnow":            _geo(50.01, 21.01),
    "krakau":            _geo(50.06, 19.94),
    "katowice":          _geo(50.26, 19.02),
    "kattowitz":         _geo(50.26, 19.02),
    "gleiwitz":          _geo(50.29, 18.67),
    "breslau":           _geo(51.11, 17.04),
    "oppeln":            _geo(50.67, 17.92),
    "neisse":            _geo(50.47, 17.92),
    "glatz":             _geo(50.43, 16.66),
    "hirschberg":        _geo(50.91, 15.72),
    "liegnitz":          _geo(51.21, 16.16),
    "görlitz":           _geo(51.15, 14.99),
    "bunzlau":           _geo(51.40, 15.95),
    "stargard":          _geo(53.34, 15.04),
    "schneidemühl":      _geo(53.15, 16.73),
    "landsberg":         _geo(52.74, 15.22),
    "küstrin":           _geo(52.59, 14.65),
    "frankfurt/oder":    _geo(52.35, 14.55),
    "ostende":           _geo(51.23,  2.92),   # belgische Küstenstadt
    # ── Nordeuropa ──
    "oslo":              _geo(59.91, 10.75),
    "bergen":            _geo(60.39,  5.32),
    "narvik":            _geo(68.44, 17.43),
    "trondheim":         _geo(63.43, 10.40),
    "stavanger":         _geo(58.97,  5.73),
    "helsinki":          _geo(60.17, 24.94),
    "vyborg":            _geo(60.71, 28.75),
    "wiborg":            _geo(60.71, 28.75),
    "petsamo":           _geo(69.52, 31.15),
    # ── Südfront: Mittelmeer / Balkan ──
    "bologna":           _geo(44.49, 11.34),
    "rimini":            _geo(44.06, 12.57),
    "ancona":            _geo(43.62, 13.50),
    "cassino":           _geo(41.49, 13.83),
    "monte cassino":     _geo(41.49, 13.83),
    "anzio":             _geo(41.45, 12.63),
    "anzio/nettuno":     _geo(41.45, 12.63),
    "nettuno":           _geo(41.46, 12.66),
    "neapel":            _geo(40.85, 14.27),
    "neapol":            _geo(40.85, 14.27),
    "salerno":           _geo(40.68, 14.75),
    "tarent":            _geo(40.46, 17.25),
    "brindisi":          _geo(40.64, 17.94),
    "palermo":           _geo(38.12, 13.36),
    "catania":           _geo(37.50, 15.09),
    "messina":           _geo(38.19, 15.55),
    "athen":             _geo(37.98, 23.73),
    "korfu":             _geo(39.62, 19.92),
    "kreta":             _geo(35.24, 24.81, 120, "region"),
    "heraklion":         _geo(35.34, 25.14),
    "canea":             _geo(35.51, 24.02),
    "saloniki":          _geo(40.64, 22.94),
    "piräus":            _geo(37.95, 23.65),
    "belgrad":           _geo(44.82, 20.46),
    "agram":             _geo(45.81, 15.98),
    "sarajewo":          _geo(43.85, 18.36),
    "sarajevo":          _geo(43.85, 18.36),
    "laibach":           _geo(46.05, 14.51),
    "ljubljana":         _geo(46.05, 14.51),
    "split":             _geo(43.51, 16.44),
    "spalato":           _geo(43.51, 16.44),
    "mostar":            _geo(43.34, 17.80),
    "skopje":            _geo(41.99, 21.43),
    "skoplje":           _geo(41.99, 21.43),
    "sofia":             _geo(42.70, 23.32),
    "bukarest":          _geo(44.43, 26.10),
    "ploiesti":          _geo(44.94, 26.03),
    "klausenburg":       _geo(46.77, 23.59),
    "hermannstadt":      _geo(45.79, 24.15),
    "kronstadt":         _geo(45.65, 25.61),
    "przemysl":          _geo(49.78, 22.78),
    "sanok":             _geo(49.56, 22.21),
    # ── Nordafrika ──
    "tobruk":            _geo(32.08, 23.97),
    "bengasi":           _geo(32.11, 20.07),
    "tripolis":          _geo(32.90, 13.18),
    "el alamein":        _geo(30.83, 28.95),
    "tunis":             _geo(36.82, 10.17),
    "sfax":              _geo(34.74, 10.76),
    "bizerta":           _geo(37.28,  9.87),
    "kasserine":         _geo(35.17,  8.83),
    # ── Regionen / Flüsse als Kampfgebiete ──
    "eifel":             _geo(50.20,  6.60, 80, "region"),
    "saarpfalz":         _geo(49.30,  7.10, 60, "region"),
    "wolchow":           _geo(59.00, 31.60, 80, "region"),
    "newel":             _geo(56.01, 29.94),
    "gshatsk":           _geo(55.58, 34.98),
    "gsazk":             _geo(55.58, 34.98),
    "mius":              _geo(47.80, 38.70, 60, "region"),
    "donez":             _geo(48.00, 37.50, 100, "region"),
    "donetz":            _geo(48.00, 37.50, 100, "region"),
    "moskau":            _geo(55.75, 37.62, 50),
    "shitomir":          _geo(50.25, 28.66),
    "welish":            _geo(55.64, 31.21),
    "demjansk":          _geo(57.65, 32.45, 40, "region"),
    "baranow":           _geo(50.49, 21.54),
    "nikopol":           _geo(47.57, 34.40),
    "polozk":            _geo(55.49, 28.79),
    "wjasma":            _geo(55.21, 34.29),
    "brody":             _geo(50.08, 25.15),
    "opotschka":         _geo(56.71, 28.66),
    "samland":           _geo(54.85, 20.80, 60, "region"),
    "welikije-luki":     _geo(56.34, 30.54),
    "welikije luki":     _geo(56.34, 30.54),
    "budapest":          _geo(47.50, 19.04),
    "karpaten":          _geo(48.50, 24.00, 150, "region"),
    "ladoga":            _geo(60.80, 31.50, 100, "region"),
    "siebenbürgen":      _geo(46.50, 24.00, 150, "region"),
    "ruhrkessel":        _geo(51.50,  7.50, 80, "region"),
    "istrien":           _geo(45.20, 13.90, 60, "region"),
    "ligurien":          _geo(44.30,  8.30, 80, "region"),
    "vogesen":           _geo(48.20,  7.00, 80, "region"),
    "beschiden":         _geo(49.50, 22.50, 100, "region"),
    "beskiden":          _geo(49.50, 22.50, 100, "region"),
    "oranienbaum":       _geo(59.92, 29.08),
    "livland":           _geo(57.50, 25.50, 150, "region"),
    "kanalküste":        _geo(50.80,  1.80, 100, "region"),
    "niederlande":       _geo(52.20,  5.30, 150, "region"),
    "kroatien":          _geo(45.50, 16.00, 150, "region"),
    "belgien":           _geo(50.50,  4.50, 100, "region"),
    "serbien":           _geo(44.00, 21.00, 150, "region"),
    "dänemark":          _geo(56.00, 10.00, 200, "region"),
    "litauen":           _geo(55.50, 24.00, 150, "region"),
    "lettland":          _geo(57.00, 25.00, 150, "region"),
    "libyen":            _geo(27.00, 17.00, 400, "region"),
    "ostfrankreich":     _geo(48.50,  7.00, 150, "region"),
    "westfrankreich":    _geo(47.50, -1.00, 200, "region"),
    "südpolen":          _geo(50.00, 21.00, 150, "region"),
    "westfrankreich":    _geo(47.50, -1.00, 200, "region"),
    # ── Spezielle Kessel / Schlachten ──
    "weichsel":          _geo(51.50, 21.50, 150, "region"),
    "wolga":             _geo(48.70, 44.50, 100, "region"),
    "don":               _geo(48.00, 41.00, 150, "region"),
    "dnjepr":            _geo(48.50, 34.00, 150, "region"),
    "oder":              _geo(52.00, 14.50, 100, "region"),
    "elbe":              _geo(52.00, 12.00, 100, "region"),
    "spree":             _geo(52.50, 13.50, 50, "region"),
    "rhein":             _geo(50.00,  7.50, 100, "region"),
    "ardennen":          _geo(50.00,  5.50, 80, "region"),
    "elsaß":             _geo(48.50,  7.50, 80, "region"),
    "normandie":         _geo(49.10, -0.40, 100, "region"),
    "bretagne":          _geo(48.00, -2.75, 100, "region"),
}


def _build_historisch_index(entries: list[dict]) -> dict[str, dict]:
    idx: dict[str, dict] = {}
    for e in entries:
        key = e["name_historisch"].strip().lower()
        val = {"lat": e["lat"], "lon": e["lon"],
               "precision": e["precision"], "radius_km": e["radius_km"],
               "source": "gazeteer_historisch"}
        idx[key] = val
        if e.get("name_modern"):
            idx[e["name_modern"].strip().lower()] = val
    return idx


def _build_regionen_index(entries: list[dict]) -> dict[str, dict]:
    idx: dict[str, dict] = {}
    for e in entries:
        key = e["name"].strip().lower()
        idx[key] = {"lat": e["lat"], "lon": e["lon"],
                    "precision": e["precision"], "radius_km": e["radius_km"],
                    "source": "gazeteer_regionen"}
    return idx


def _load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _geonames_lookup(name: str) -> dict | None:
    if not GEONAMES_USER:
        return None
    params = urllib.parse.urlencode({
        "q": name, "maxRows": 1, "username": GEONAMES_USER,
        "featureClass": "P", "type": "json",
    })
    url = f"http://api.geonames.org/searchJSON?{params}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        hits = data.get("geonames", [])
        if hits:
            h = hits[0]
            return {"lat": float(h["lat"]), "lon": float(h["lng"]),
                    "precision": "stadt", "radius_km": 20, "source": "geonames"}
    except Exception:
        pass
    return None


def _preprocess(name: str) -> list[str]:
    """Leitet mehrere Suchvarianten aus einem Ortsnamen ab."""
    s = name.strip()

    # Klammern ganz am Anfang/Ende entfernen und Inhalt extrahieren
    # "(Leningrad)Osten" → ["Leningrad", "Osten"]
    candidates = [s]

    # Geklammerten Teil extrahieren, wenn Name mit ( beginnt
    m = re.match(r'^\(([^)]+)\)(.*)$', s)
    if m:
        candidates.append(m.group(1).strip())
        if m.group(2).strip():
            candidates.append(m.group(2).strip())

    # Klammern am Ende entfernen: "Orel (Brjansk)" → "Orel"
    m2 = re.match(r'^([^(]+)\s*\([^)]+\)\s*$', s)
    if m2:
        candidates.append(m2.group(1).strip())

    # Komma-Split: "Aachen, Eifel" → "Aachen"
    if ',' in s:
        candidates.append(s.split(',')[0].strip())

    # Slash-Split: "Anzio/Nettuno" → "Anzio"
    if '/' in s:
        candidates.append(s.split('/')[0].strip())

    # Bindestrich-Präfix/Suffix entfernen: "Nord-" → raus; "Spass-Demensk" bleibt
    s_stripped = s.rstrip('-').lstrip('-')
    if s_stripped != s:
        candidates.append(s_stripped)

    # Entferne führende/nachfolgende Sonderzeichen
    s_clean = re.sub(r'^[^a-zA-ZÄÖÜäöüßА-Яа-я]+', '', s)
    s_clean = re.sub(r'[^a-zA-ZÄÖÜäöüßА-Яа-я0-9]+$', '', s_clean)
    if s_clean and s_clean != s:
        candidates.append(s_clean)

    # "Osten Krementschug" / "Osten Mirgorod" → Ortsname nach "Osten "
    m_osten = re.match(r'^(?:Osten|Westen)\s+(.{3,})$', s)
    if m_osten:
        candidates.append(m_osten.group(1).strip())

    # Duplikate entfernen, leere entfernen
    seen = set()
    result = []
    for c in candidates:
        c = c.strip()
        if c and c not in seen:
            seen.add(c)
            result.append(c)
    return result


_SCHAUPLATZ_LOWER = {s.lower() for s in SCHAUPLATZ}


def _is_schauplatz(name: str) -> bool:
    if name in SCHAUPLATZ:
        return True
    nl = name.lower()
    if nl in _SCHAUPLATZ_LOWER:
        return True
    # Präfix-Check: nur wenn Präfix ein vollständiges Wort ist (Leerzeichen, Bindestrich, _, Ende)
    for prefix in _SCHAUPLATZ_PREFIXES:
        if name == prefix:
            return True
        if re.match(r'^' + re.escape(prefix) + r'[\s\-_/|]', name):
            return True
    # Nur Ziffern, Sonderzeichen, Sternchen — kein auflösbarer Ortsname
    if re.match(r'^[\d\s\W]+$', name):
        return True
    # Reine Großbuchstaben-Kürzel: "BdE", "OKH", "WKV", "XXXIX" etc.
    if re.match(r'^[A-ZÄÖÜ0-9]{2,8}[\.\-]?$', name):
        return True
    return False


def resolve(name: str,
            hist_idx: dict[str, dict],
            reg_idx: dict[str, dict],
            cache: dict[str, dict]) -> dict | None:
    if not name or not name.strip():
        return None

    orig_key = name.strip().lower()

    # Cache
    if orig_key in cache:
        return cache[orig_key]

    # Schauplatz-Blacklist (direkt)
    if _is_schauplatz(name.strip()):
        result = {"precision": "schauplatz", "source": "blacklist"}
        cache[orig_key] = result
        return result

    # Varianten erzeugen
    variants = _preprocess(name)

    for variant in variants:
        if not variant:
            continue
        vkey = variant.lower()

        # Schauplatz für Variante prüfen
        if _is_schauplatz(variant):
            continue

        # 1. Exakt in internem Dict
        if vkey in _GEO_EXTENDED:
            r = {**_GEO_EXTENDED[vkey]}
            cache[orig_key] = r
            return r

        # 2. Exakt in historisch
        if vkey in hist_idx:
            r = {**hist_idx[vkey]}
            cache[orig_key] = r
            return r

        # 3. Exakt in regionen
        if vkey in reg_idx:
            r = {**reg_idx[vkey]}
            cache[orig_key] = r
            return r

    # Fuzzy: historisch-Key als Substring im ersten Variant
    primary = variants[0].lower() if variants else orig_key
    for hkey, hval in hist_idx.items():
        if len(hkey) >= 4 and hkey in primary:
            r = {**hval, "source": "gazeteer_historisch_fuzzy"}
            cache[orig_key] = r
            return r

    # Fuzzy: internes Dict
    for gkey, gval in _GEO_EXTENDED.items():
        if len(gkey) >= 4 and gkey in primary:
            r = {**gval, "source": "internal_fuzzy"}
            cache[orig_key] = r
            return r

    # Fuzzy: regionen
    for rkey, rval in reg_idx.items():
        if len(rkey) >= 4 and rkey in primary:
            r = {**rval, "source": "gazeteer_regionen_fuzzy"}
            cache[orig_key] = r
            return r

    # GeoNames
    gn = _geonames_lookup(variants[0] if variants else name)
    if gn:
        cache[orig_key] = gn
        return gn

    return None


def main() -> None:
    hist_idx = _build_historisch_index(_load_json(HISTORISCH))
    reg_idx  = _build_regionen_index(_load_json(REGIONEN))

    cache: dict[str, dict] = {}
    if CACHE_FILE.exists():
        with open(CACHE_FILE, encoding="utf-8") as f:
            cache = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT id, data FROM events WHERE type='UnitJoining' AND (lat IS NULL OR lon IS NULL)"
    ).fetchall()

    print(f"UnitJoining-Events ohne Koordinaten: {len(rows)}")

    stats: dict[str, int] = {
        "schauplatz": 0, "internal": 0, "internal_fuzzy": 0,
        "historisch": 0, "historisch_fuzzy": 0,
        "regionen": 0, "regionen_fuzzy": 0,
        "geonames": 0, "unresolved": 0,
    }
    unresolved_names: list[str] = []
    updated = 0

    for row in rows:
        ev = json.loads(row["data"])
        place = ev.get("place") or {}
        ort_name = place.get("name") or ""
        if not ort_name:
            stats["unresolved"] += 1
            continue

        result = resolve(ort_name, hist_idx, reg_idx, cache)

        if result is None:
            if ort_name not in unresolved_names:
                unresolved_names.append(ort_name)
            stats["unresolved"] += 1
            continue

        src = result.get("source", "unresolved")
        if src == "blacklist":
            stats["schauplatz"] += 1
            continue

        # Stat-Bucket
        src_bucket = (
            src.replace("gazeteer_historisch", "historisch")
               .replace("gazeteer_regionen", "regionen")
        )
        if src_bucket in stats:
            stats[src_bucket] += 1
        else:
            stats["geonames"] += 1

        place["lat"]       = result["lat"]
        place["lon"]       = result["lon"]
        place["precision"] = result["precision"]
        place["radius_km"] = result.get("radius_km", 20)
        ev["place"] = place

        conn.execute(
            "UPDATE events SET lat=?, lon=?, data=? WHERE id=?",
            (result["lat"], result["lon"],
             json.dumps(ev, ensure_ascii=False), row["id"]),
        )
        updated += 1

    conn.commit()
    conn.close()

    _save_json(CACHE_FILE, cache)
    _save_json(UNRESOLVED, sorted(set(unresolved_names)))

    # Bericht
    total = sum(stats.values())
    resolved_count = total - stats["unresolved"]
    pct = resolved_count / total * 100 if total else 0

    print("\n── Geocoding-Ergebnis ──────────────────────────────────────")
    print(f"  Verarbeitet gesamt:            {total}")
    print(f"  Aktualisiert in DB:            {updated}")
    print(f"  ├─ intern (exakt):             {stats['internal']}")
    print(f"  ├─ intern (fuzzy):             {stats['internal_fuzzy']}")
    print(f"  ├─ gazeteer_historisch:        {stats['historisch']} + {stats['historisch_fuzzy']} fuzzy")
    print(f"  ├─ gazeteer_regionen:          {stats['regionen']} + {stats['regionen_fuzzy']} fuzzy")
    print(f"  ├─ geonames:                   {stats['geonames']}")
    print(f"  ├─ schauplatz (korrekt leer):  {stats['schauplatz']}")
    print(f"  └─ nicht aufgelöst:            {stats['unresolved']}")
    print(f"\n  Abdeckung (alle):              {pct:.1f} %")
    print(f"  Abdeckung (exkl. schauplatz):  "
          f"{(resolved_count - stats['schauplatz']) / max(1, total - stats['schauplatz']) * 100:.1f} %")
    print(f"\n  nicht_aufgeloest.json: {len(unresolved_names)} einzigartige Namen")


if __name__ == "__main__":
    main()
