"""
test_pipeline.py — Tests für pipeline_b.py

Führe aus mit:
    pytest test_pipeline.py -v

Testdaten (im Projektverzeichnis, nicht im Git):
  - "Koppermann, Hans-Jürgen_B 563-1 KARTEI_K_1458_033.pdf"     (WASt-Karteikarte, nur Bilder)
  - "2021-G-12837, Koppermann, Hans-Jürgen 02.09.1917 u.A. Kopfbogen neu 2020.pdf"
    (Bundesarchiv-Auskunftsschreiben, Maschinentext)

Umgebungsvariablen:
  ANTHROPIC_API_KEY — für B3-Tests (WASt Vision). Ohne Key werden B3-Tests übersprungen.
"""

import os
import subprocess
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import pytest

import json

from pipeline_b import (
    classify_pdf,
    extract_bundesarchiv,
    ingest_bundesarchiv,
    extract_wast,
    ingest_wast,
)
from abbreviations import resolve_abbreviations, add_user_abbreviation, ABBREV_FILE

# Echte Dateinamen (Leerzeichen + Sonderzeichen wie im Dateisystem)
WAST_PDF = Path("Koppermann, Hans-Jürgen_B 563-1 KARTEI_K_1458_033.pdf")
AUSKUNFT_PDF = Path("2021-G-12837, Koppermann, Hans-Jürgen 02.09.1917 u.A. Kopfbogen neu 2020.pdf")


@pytest.fixture(autouse=True)
def require_pdfs():
    """Überspringt Tests wenn die PDFs nicht vorhanden sind."""
    missing = [p for p in [WAST_PDF, AUSKUNFT_PDF] if not p.exists()]
    if missing:
        pytest.skip(f"PDF nicht gefunden: {[str(p) for p in missing]}")


@pytest.fixture
def require_api_key():
    """Überspringt Tests wenn ANTHROPIC_API_KEY nicht gesetzt ist."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY nicht gesetzt — B3-Tests übersprungen")


# ─── Klassifizierung ─────────────────────────────────────────────────────────

def test_classify_wast():
    typ, conf = classify_pdf(WAST_PDF)
    assert typ == "wast_karteikarte"
    assert conf > 0.9


def test_classify_auskunft():
    typ, conf = classify_pdf(AUSKUNFT_PDF)
    assert typ == "bundesarchiv_auskunft"
    assert conf > 0.9


# ─── Extraktion ──────────────────────────────────────────────────────────────

def test_extract_personen():
    result = extract_bundesarchiv(AUSKUNFT_PDF)

    assert len(result["persons"]) == 2

    p0 = result["persons"][0]
    assert p0["name"] == "Koppermann, Hans-Jürgen"
    assert p0["birth_date"] == "1917-09-02"
    assert p0["actor_id"] == "person_koppermann_hj_1917"
    assert len(p0["einheitsmeldungen"]) == 8

    # Stichprobe: erste und letzte Meldung
    em_first = p0["einheitsmeldungen"][0]
    assert em_first["einheit"] == "1. Kompanie Nachrichten-Abteilung 20"
    assert em_first["jahr"] == 1939
    assert em_first["signatur"] == "B 563/40425"

    em_last = p0["einheitsmeldungen"][-1]
    assert "Grenadier-Ersatz-Bataillon" in em_last["einheit"]
    assert em_last["jahr"] == 1943

    p1 = result["persons"][1]
    assert p1["name"] == "Heinrich, Martin Ludwig Franz"
    assert p1["birth_date"] == "1920-11-17"
    assert p1["actor_id"] == "person_heinrich_mlf_1920"


def test_extract_source():
    result = extract_bundesarchiv(AUSKUNFT_PDF)
    src = result["source"]
    assert src["type"] == "bundesarchiv"
    assert src["certainty"] == 4
    assert src["generated_by"] == "direkt"
    assert "PA 2 2021/G-12837" in src["reference"]


# ─── Ingest ──────────────────────────────────────────────────────────────────

def test_ingest_in_db():
    ids = ingest_bundesarchiv(AUSKUNFT_PDF)
    assert "person_koppermann_hj_1917" in ids
    assert "person_heinrich_mlf_1920" in ids


# ─── Gesamtvalidierung ───────────────────────────────────────────────────────

def test_validate():
    result = subprocess.run(
        ["python3", "validate.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"validate.py fehlgeschlagen:\n{result.stdout}\n{result.stderr}"
    )


# ─── B3 WASt Vision ──────────────────────────────────────────────────────────

def test_extract_wast(require_api_key):
    result = extract_wast(WAST_PDF)

    assert len(result["pages"]) >= 3

    vorderseite = result["pages"][0]
    assert vorderseite["familienname"] == "Koppermann"
    assert vorderseite["vorname"] == "Hans-Jürgen"
    assert vorderseite["geboren_am"] == "1917-09-02"
    assert len(vorderseite["meldungen"]) >= 1

    src = result["source"]
    assert src["type"] == "wast"
    assert src["certainty"] == 5


def test_ingest_wast(require_api_key):
    ingest_wast(WAST_PDF)

    from db import verorte
    events = verorte("person_koppermann_hj_1917", "1943-08-28")
    assert any(e["type"] == "Wounding" for e in events)


# ─── B4 Abkürzungsauflösung ──────────────────────────────────────────────────

def test_abbreviations_basic():
    result = resolve_abbreviations("Gr.Spli.Verl. Hals + re. Ohr")
    assert "Gr.Spli.Verl." in result["found"]
    assert result["found"]["Gr.Spli.Verl."] == "Granatsplitter-Verwundung"


def test_abbreviations_unresolved():
    result = resolve_abbreviations("Xyz. unbekannte Abk.")
    assert "Xyz." in result["unresolved"]


def test_add_user_abbreviation():
    add_user_abbreviation("Test.Abk.", "Test-Auflösung")
    try:
        result = resolve_abbreviations("Test.Abk. im Text")
        assert "Test.Abk." in result["found"]
        assert result["found"]["Test.Abk."] == "Test-Auflösung"
    finally:
        data = json.loads(ABBREV_FILE.read_text(encoding="utf-8"))
        data["benutzerdefiniert"].pop("Test.Abk.", None)
        ABBREV_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ─── B3 WASt Vision ──────────────────────────────────────────────────────────

def test_wast_quality_vs_goldstandard(require_api_key):
    result = extract_wast(WAST_PDF)

    checks = {
        "familienname": result["pages"][0].get("familienname") == "Koppermann",
        "vorname": result["pages"][0].get("vorname") == "Hans-Jürgen",
        "geboren_am": result["pages"][0].get("geboren_am") == "1917-09-02",
        "geburtsort": result["pages"][0].get("geburtsort") == "Hannover",
        "truppenteil_enthaelt_90": "90" in str(result["pages"][0].get("truppenteil", "")),
        "anzahl_meldungen_mindestens_8": len([
            m for p in result["pages"][:2]
            for m in p.get("meldungen", [])
        ]) >= 8,
        "verwundung_datum_1943_08_28": any(
            "1943-08-28" in str(m.get("ereignis_datum", ""))
            for p in result["pages"] for m in p.get("meldungen", [])
        ),
        "radom_erwaehnt": any(
            "Radom" in str(m.get("inhalt_original", ""))
            for p in result["pages"] for m in p.get("meldungen", [])
        ),
        "marburg_erwaehnt": any(
            "Marburg" in str(m.get("inhalt_original", ""))
            for p in result["pages"] for m in p.get("meldungen", [])
        ),
        "vermisst_1945": any(
            "1945" in str(m.get("ereignis_datum", "")) or
            "45" in str(m.get("inhalt_original", ""))
            for p in result["pages"] for m in p.get("meldungen", [])
        ),
    }

    score = sum(checks.values()) / len(checks)
    print(f"\nQualität B3: {sum(checks.values())}/{len(checks)} = {score:.0%}")
    for check, ok in checks.items():
        print(f"  {'✓' if ok else '✗'} {check}")

    assert score >= 0.8, f"Qualität unter 80%: {score:.0%}"
