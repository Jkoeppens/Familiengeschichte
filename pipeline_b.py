#!/usr/bin/env python3
"""
pipeline_b.py — Dokumenten-Eingangspipeline für Bundesarchiv-Auskunftsschreiben und WASt-Karteikarten.

Drei öffentliche Funktionen:
  classify_pdf(pdf_path)         → (typ, konfidenz)
  extract_bundesarchiv(pdf_path) → dict mit persons + source
  ingest_bundesarchiv(pdf_path)  → list[actor_id]
"""

import base64
import json as _json
import re
import sqlite3
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import jsonschema

import fitz          # PyMuPDF
import pdfplumber
import anthropic as _anthropic

import db
from abbreviations import resolve_abbreviations
from geocode import geocode as _geocode


# ─── Text-Extraktion ──────────────────────────────────────────────────────────

def _extract_text(pdf_path: str | Path) -> str:
    with pdfplumber.open(pdf_path) as doc:
        return "\n".join(pg.extract_text() or "" for pg in doc.pages)


# ─── 1. classify_pdf ──────────────────────────────────────────────────────────

def classify_pdf(pdf_path: str | Path) -> tuple[str, float]:
    """Klassifiziert PDF nach Typ. Gibt (typ, konfidenz) zurück."""
    text = _extract_text(pdf_path)
    if len(text) < 100:
        return "wast_karteikarte", 0.95
    tl = text.lower()
    if "bundesarchiv" in tl and "betreff" in tl:
        return "bundesarchiv_auskunft", 0.95
    if "lazarett" in tl and "krankenbuch" in tl:
        return "lazarettbuch", 0.80
    return "unbekannt", 0.0


# ─── Hilfsfunktionen ─────────────────────────────────────────────────────────

def _parse_date_de(s: str) -> Optional[str]:
    """'02.09.1917' → '1917-09-02'"""
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", s.strip())
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def _normalize_id_part(s: str) -> str:
    """String zu [a-z0-9] normalisieren für ID-Segmente."""
    s = s.lower()
    for src, dst in [("ü", "ue"), ("ö", "oe"), ("ä", "ae"), ("ß", "ss")]:
        s = s.replace(src, dst)
    return re.sub(r"[^a-z0-9]", "", s)


def _make_person_id(family: str, given: str, year: str) -> str:
    """
    Erzeugt Actor-ID nach Schema-Konvention.
    'Koppermann', 'Hans-Jürgen', '1917' → 'person_koppermann_hj_1917'
    'Heinrich', 'Martin Ludwig Franz', '1920' → 'person_heinrich_mlf_1920'
    """
    fam = _normalize_id_part(family)
    parts = re.split(r"[\s\-]+", given)
    initials = "".join(
        _normalize_id_part(p)[0]
        for p in parts
        if p and _normalize_id_part(p)
    )
    return f"person_{fam}_{initials}_{year}"


def _parse_persons_from_betreff(text: str) -> list[dict]:
    """Extrahiert Personen aus dem BETREFF-Block des Schreibens."""
    persons = []
    # Muster: "1.) Nachname, Vorname(n), geboren am TT.MM.JJJJ"
    pattern = re.compile(
        r"\d+\.\)\s+([A-ZÄÖÜ][^,\n]+),\s+([^,\n]+),\s+geboren am\s+(\d{2}\.\d{2}\.\d{4})"
    )
    for m in pattern.finditer(text):
        family = m.group(1).strip()
        given = m.group(2).strip()
        bdate = _parse_date_de(m.group(3))
        year = bdate[:4] if bdate else None
        actor_id = _make_person_id(family, given, year) if year else None
        persons.append({
            "name": f"{family}, {given}",
            "family_name": family,
            "given_name": given,
            "birth_date": bdate,
            "actor_id": actor_id,
            "einheitsmeldungen": [],
        })
    return persons


def _normalize_section(text: str) -> str:
    """Entfernt Seitenmarken und korrigiert OCR-Leerzeichen-Artefakte."""
    # "SEITE 3 • ..." → "• ..."
    text = re.sub(r"SEITE\s+\d+\s*", "", text)
    # "Sc hützen" → "Schützen": Leerzeichen zwischen zwei Kleinbuchstaben entfernen
    text = re.sub(r"(?<=[a-zäöüß]) (?=[a-zäöüß])", "", text)
    return text


def _parse_einheitsmeldungen(section_text: str) -> list[dict]:
    """
    Parst Bullet-Einträge aus dem Abschnitt einer Person.
    Format im PDF (zweispaltig, pdfplumber bringt beide Spalten auf eine Zeile):

        • Einheitsname gemeldet: Bundesarchivsignatur:
        JJJJ B 563/XXXXX

    Bei umbrochenen Einheitsnamen (PDF-Zeilenumbruch mit Bindestrich):

        • Stamm-Kompanie Nachrichten-Ersatz-Ab- gemeldet: Bundesarchivsignatur:
        teilung 20 1942 B 563/40291
    """
    text = _normalize_section(section_text)
    lines = text.split("\n")
    entries = []

    for i, line in enumerate(lines):
        line = line.strip()
        if not line.startswith("•"):
            continue
        content = line[1:].strip()

        # Nur Einheitsmeldungs-Bullets; Literatur-Bullets etc. überspringen
        if "gemeldet: Bundesarchivsignatur:" not in content:
            continue

        idx = content.index("gemeldet: Bundesarchivsignatur:")
        unit_part = content[:idx].rstrip()
        next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""

        # Fall 1: nächste Zeile beginnt direkt mit Jahr + Signatur
        m_direct = re.match(r"^(19\d{2})\s+(B\s*\d{3}/\d+)", next_line)
        if m_direct:
            unit_name = unit_part.rstrip("-").strip()
            year = int(m_direct.group(1))
            sig = re.sub(r"\s+", " ", m_direct.group(2))
        else:
            # Fall 2: nächste Zeile enthält Fortsetzung des Namens + Jahr + Signatur
            # z.B. "teilung 20 1942 B 563/40291"
            m_year = re.search(r"\b(19\d{2})\b", next_line)
            m_sig = re.search(r"(B\s*\d{3}/\d+)", next_line)
            if not (m_year and m_sig):
                continue
            continuation = next_line[:m_year.start()].strip()
            if unit_part.endswith("-"):
                # Bindestrich-Umbruch: "Ab-" + "teilung" → "Abteilung"
                unit_name = unit_part[:-1] + continuation
            else:
                unit_name = (unit_part + " " + continuation).strip()
            unit_name = " ".join(unit_name.split())
            year = int(m_year.group(1))
            sig = re.sub(r"\s+", " ", m_sig.group(1))

        entries.append({"einheit": unit_name, "jahr": year, "signatur": sig})

    return entries


# ─── 2. extract_bundesarchiv ─────────────────────────────────────────────────

def extract_bundesarchiv(pdf_path: str | Path) -> dict:
    """
    Extrahiert strukturierte Daten aus einem Bundesarchiv-Auskunftsschreiben.

    Gibt zurück:
    {
        "persons": [{"name", "family_name", "given_name", "birth_date", "actor_id",
                     "einheitsmeldungen": [{"einheit", "jahr", "signatur"}]}],
        "source": {"type", "reference", "certainty", "generated_by"},
        "letter_date": "JJJJ-MM-TT"
    }
    """
    text = _extract_text(pdf_path)

    # Aktenzeichen: "MEIN ZEICHEN PA 2 2021/ G-12837"
    ref_m = re.search(r"PA\s+\d+\s+\d{4}/\s*G-\d+", text)
    reference = None
    if ref_m:
        reference = re.sub(r"\s+", " ", ref_m.group(0))
        reference = re.sub(r"/\s+G", "/G", reference)

    # Datum des Schreibens
    date_m = re.search(r"DATUM\s+(\d{2}\.\d{2}\.\d{4})", text)
    letter_date = _parse_date_de(date_m.group(1)) if date_m else None

    # Personen aus BETREFF
    persons = _parse_persons_from_betreff(text)

    # Text nach "zu N.)" aufteilen → Abschnitte pro Person
    # sections[0] = Header, sections[1] = Person 1, sections[2] = Person 2, ...
    sections = re.split(r"zu\s+\d+\.\)", text)
    for i, person in enumerate(persons):
        if i + 1 < len(sections):
            person["einheitsmeldungen"] = _parse_einheitsmeldungen(sections[i + 1])

    # Abkürzungen in Einheitsnamen auflösen
    unresolved: set[str] = set()
    for person in persons:
        for em in person.get("einheitsmeldungen", []):
            r = resolve_abbreviations(em["einheit"])
            em["abbrev"] = r["found"]
            unresolved.update(r["unresolved"])

    return {
        "persons": persons,
        "source": {
            "type": "bundesarchiv",
            "reference": reference,
            "certainty": 4,
            "generated_by": "direkt",
        },
        "letter_date": letter_date,
        "unresolved_abbreviations": sorted(unresolved),
    }


# ─── 3. ingest_bundesarchiv ──────────────────────────────────────────────────

_ERROR_QUEUE = Path(__file__).parent / "error_queue.json"


def _validate_and_commit(
    events: list,
    participations: list,
    source_file: str,
) -> bool:
    """
    Validates events and participations against JSON schema.
    On success: writes to DB. On failure: logs to error_queue.json.
    Returns True on success, False on failure.
    """
    errors = []

    for e in events:
        try:
            db._validate(e, "event")
        except jsonschema.ValidationError as err:
            errors.append({
                "file": source_file,
                "object_id": e.get("id"),
                "error": err.message,
                "path": list(err.absolute_path),
            })

    for p in participations:
        try:
            db._validate(p, "participation")
        except jsonschema.ValidationError as err:
            errors.append({
                "file": source_file,
                "object_id": f"{p.get('event_id')}+{p.get('actor_id')}",
                "error": err.message,
                "path": list(err.absolute_path),
            })

    if errors:
        queue: list = _json.loads(_ERROR_QUEUE.read_text(encoding="utf-8")) if _ERROR_QUEUE.exists() else []
        queue.append({
            "timestamp": datetime.now().isoformat(),
            "source_file": source_file,
            "error_count": len(errors),
            "errors": errors,
        })
        _ERROR_QUEUE.write_text(_json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✗ {len(errors)} Validierungsfehler — Dokument in error_queue.json, nicht in DB")
        return False

    for e in events:
        db.insert_event(e)
    for p in participations:
        db.insert_participation(p)
    print(f"✓ {len(events)} Events, {len(participations)} Participations in DB")
    return True


def _actor_exists(conn: sqlite3.Connection, actor_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM actors WHERE id=?", (actor_id,)
    ).fetchone() is not None


def ingest_bundesarchiv(pdf_path: str | Path) -> list[str]:
    """
    Lädt Bundesarchiv-Auskunft in familiengeschichte.db.

    - Pro Person: Actor anlegen falls nicht vorhanden
    - Pro Einheitsmeldung: PersonJoining-Event + Participation
    - Gibt Liste aller verarbeiteten Actor-IDs zurück
    """
    data = extract_bundesarchiv(pdf_path)
    today = date.today().isoformat()
    actor_ids: list[str] = []
    events: list[dict] = []
    participations: list[dict] = []

    for person in data["persons"]:
        actor_id = person["actor_id"]
        if not actor_id:
            continue

        with db._get_conn() as conn:
            if not _actor_exists(conn, actor_id):
                db.insert_actor({
                    "id": actor_id,
                    "type": "Person",
                    "pref_label": person["name"],
                    "alt_labels": [],
                    "family_name": person["family_name"],
                    "given_name": person["given_name"],
                    "birth_date": person["birth_date"],
                    "created_at": today,
                })

        actor_ids.append(actor_id)

        for em in person["einheitsmeldungen"]:
            sig_norm = re.sub(r"[^a-z0-9]", "_", em["signatur"].lower()).strip("_")
            actor_short = actor_id.replace("person_", "")
            event_id = f"event_pj_{actor_short}_{sig_norm}_{em['jahr']}"

            events.append({
                "id": event_id,
                "type": "PersonJoining",
                "label": f"{person['name']} bei {em['einheit']}",
                "time_span": {
                    "begin": str(em["jahr"]),
                    "end": str(em["jahr"]),
                    "precision": "year",
                },
                "source": {
                    "type": "bundesarchiv",
                    "reference": em["signatur"],
                    "certainty": 4,
                    "generated_by": "direkt",
                },
                "created_at": today,
            })
            participations.append({
                "event_id": event_id,
                "actor_id": actor_id,
                "relation": "had_participant",
                "role": "soldier",
                "created_at": today,
            })

    _validate_and_commit(events, participations, str(pdf_path))
    return actor_ids


# ─── Ortsextraktion aus Meldungstexten ───────────────────────────────────────

PLACE_PATTERNS = [
    # "Rela. Radom, Lkb. 23787" oder "Rela. Marburg" (auch am Zeilenende)
    r'Rela\.?\s+([A-ZÄÖÜ][a-zA-Züöäß\-]+)(?:[\s,]|$)',
    # "Res. Laz. III Marburg/Lahn" → Marburg/Lahn
    r'Laz\..*?([A-ZÄÖÜ][a-zA-Züöäß\-]+/[A-Za-z]+)',
    # "Res. Laz. III Marburg" (Fallback ohne Slash)
    r'Laz\..*?([A-ZÄÖÜ][a-zA-Züöäß\-]{3,})',
    # "Gorki etwa 35 km südostw. Ilija" → Gorki
    r'^([A-ZÄÖÜ][a-zA-Züöäß\-]+)\s+etwa',
    # "Trier, Bürgerhospital" → Trier
    r'^([A-ZÄÖÜ][a-zA-Züöäß\-]+),\s+[A-ZÄÖÜ]',
]


def _extract_place_from_meldung(
    inhalt: str,
    ort: Optional[str] = None,
) -> Optional[dict]:
    """Extrahiert Ortsangabe aus Vision-ort-Feld (Priorität) oder inhalt_original (Regex).

    Gibt {name, lat, lon, precision, radius_km} oder None zurück.
    lat/lon können None sein wenn der Ort im Gazetteer nicht gefunden wurde.
    """
    def _to_place(ort_name: str) -> Optional[dict]:
        geo = _geocode(ort_name)
        if geo is None:
            return {"name": ort_name, "lat": None, "lon": None,
                    "precision": "stadt", "radius_km": 20}
        if geo.get("source") == "blacklist":
            return None
        return {
            "name":      ort_name,
            "lat":       geo.get("lat"),
            "lon":       geo.get("lon"),
            "precision": geo.get("precision", "stadt"),
            "radius_km": geo.get("radius_km", 20),
        }

    # Priorität 1: Vision-ort
    if ort and ort.strip().lower() not in ("", "null", "none"):
        place = _to_place(ort.strip())
        if place is not None:
            return place

    # Priorität 2: Regex auf inhalt_original
    for pattern in PLACE_PATTERNS:
        m = re.search(pattern, inhalt)
        if m:
            place = _to_place(m.group(1))
            if place is not None:
                return place

    return None


# ─── B3 WASt Karteikarte (Vision) ────────────────────────────────────────────

_WAST_PROMPTS: dict[str, str] = {
    "karte_I_vorderseite": """\
Du siehst die Vorderseite einer WASt-Karteikarte (Wehrmacht-Auskunftstelle).

Die Meldungszeilen haben vier Spalten (von links nach rechts):
  1. Datum        — TT.MM.JJJJ oder MM.JJJJ oder JJJJ
  2. Ort          — Stadtname, Kreisname oder Kampfraum (z.B. "Gorki", "Trier", "Radom", "Bialystok")
                    WICHTIG: Lies diese Spalte unabhängig vom Inhalt sorgfältig aus.
                    Wenn kein Ort eingetragen ist, gib null an.
  3. Einheit      — Truppenteil / Einheit
  4. Eintragung   — Wortlaut des Eintrags (Verwundung, Hospitalisierung usw.)

Extrahiere alle sichtbaren Daten und gib NUR das folgende JSON zurück, ohne erklärenden Text darum:

{
  "card_type": "karte_I_vorderseite",
  "familienname": "Nachname oder null",
  "vorname": "Vorname(n) oder null",
  "geboren_am": "TT.MM.JJJJ oder null",
  "geburtsort": "Geburtsort oder null",
  "dienstgrad": "Dienstgrad oder null",
  "truppenteil": "Truppenteil oder null",
  "meldungen": [
    {
      "datum": "TT.MM.JJJJ oder MM.JJJJ oder JJJJ oder null",
      "ort": "Ortsname aus Spalte 2 oder null (NICHT aus der Eintragungsspalte entnehmen)",
      "einheit": "Truppenteil oder null",
      "inhalt_original": "Wortlaut der Eintragung genau wie auf der Karte"
    }
  ]
}""",
    "karte_I_rueckseite": """\
Du siehst die Rückseite einer WASt-Karteikarte (Wehrmacht-Auskunftstelle).

Die Meldungszeilen haben vier Spalten (von links nach rechts):
  1. Datum        — TT.MM.JJJJ oder MM.JJJJ oder JJJJ
  2. Ort          — Stadtname, Kreisname oder Kampfraum (z.B. "Gorki", "Trier", "Radom")
                    WICHTIG: Lies diese Spalte unabhängig vom Inhalt sorgfältig aus.
                    Wenn kein Ort eingetragen ist, gib null an.
  3. Einheit      — Truppenteil / Einheit
  4. Eintragung   — Wortlaut des Eintrags

Extrahiere alle Meldungen und gib NUR das folgende JSON zurück, ohne erklärenden Text darum:

{
  "card_type": "karte_I_rueckseite",
  "meldungen": [
    {
      "datum": "TT.MM.JJJJ oder MM.JJJJ oder JJJJ oder null",
      "ort": "Ortsname aus Spalte 2 oder null",
      "einheit": "Truppenteil oder null",
      "inhalt_original": "Wortlaut der Eintragung genau wie auf der Karte"
    }
  ]
}""",
    "karte_II": """\
Du siehst eine WASt-Karte II (Wehrmacht-Auskunftstelle).

Die Meldungszeilen haben vier Spalten (von links nach rechts):
  1. Datum        — TT.MM.JJJJ oder MM.JJJJ oder JJJJ
  2. Ort          — Stadtname, Kreisname oder Kampfraum (z.B. "Gorki", "Trier", "Radom")
                    WICHTIG: Lies diese Spalte unabhängig vom Inhalt sorgfältig aus.
                    Wenn kein Ort eingetragen ist, gib null an.
  3. Einheit      — Truppenteil / Einheit
  4. Eintragung   — Wortlaut des Eintrags

Extrahiere alle sichtbaren Daten und gib NUR das folgende JSON zurück, ohne erklärenden Text darum:

{
  "card_type": "karte_II",
  "familienname": "Nachname oder null",
  "vorname": "Vorname(n) oder null",
  "geboren_am": "TT.MM.JJJJ oder null",
  "meldungen": [
    {
      "datum": "TT.MM.JJJJ oder MM.JJJJ oder JJJJ oder null",
      "ort": "Ortsname aus Spalte 2 oder null",
      "einheit": "Truppenteil oder null",
      "inhalt_original": "Wortlaut der Eintragung genau wie auf der Karte"
    }
  ]
}""",
}


def pdf_page_to_base64(pdf_path: str | Path, page_num: int, dpi: int = 300) -> str:
    """PDF-Seite → JPEG → base64."""
    doc = fitz.open(str(pdf_path))
    pix = doc[page_num].get_pixmap(dpi=dpi)
    return base64.standard_b64encode(pix.tobytes("jpeg")).decode()


def _call_vision(b64: str, prompt: str) -> dict:
    """Claude Vision aufrufen und JSON-Antwort parsen."""
    client = _anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
                },
                {"type": "text", "text": prompt},
            ],
        }],
    )
    text = msg.content[0].text.strip()
    # Markdown-Codeblock entfernen falls vorhanden
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return _json.loads(text)


def _parse_date_partial(s: str) -> tuple[Optional[str], str]:
    """Parse partielle Datumsangabe im deutschen Format → (ISO, precision).

    '28.08.1943' → ('1943-08-28', 'day')
    '28.08.43'   → ('1943-08-28', 'day')   # WASt: zweistellig → 19XX
    '08.1943'    → ('1943-08', 'month')
    '1943'       → ('1943', 'year')
    '43'         → ('1943', 'year')
    """
    s = s.strip()
    # DD.MM.YYYY
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", s)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}", "day"
    # DD.MM.YY → 19YY (WASt-Karten: alle Einträge 1900–1945)
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{2})$", s)
    if m:
        return f"19{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}", "day"
    # MM.YYYY
    m = re.match(r"^(\d{1,2})\.(\d{4})$", s)
    if m:
        return f"{m.group(2)}-{m.group(1).zfill(2)}", "month"
    # MM.YY → 19YY
    m = re.match(r"^(\d{1,2})\.(\d{2})$", s)
    if m:
        return f"19{m.group(2)}-{m.group(1).zfill(2)}", "month"
    # YYYY
    m = re.match(r"^(\d{4})$", s)
    if m:
        return m.group(1), "year"
    # YY → 19YY
    m = re.match(r"^(\d{2})$", s)
    if m:
        return f"19{m.group(1)}", "year"
    return None, "unknown"


def _classify_meldung(inhalt: str) -> tuple[str, Optional[str]]:
    """Meldungsinhalt → (event_type, subtype).

    Gibt ("Unknown", None) für nicht klassifizierbare Einträge.
    """
    il = inhalt.lower()
    if re.search(r"gr\.spli\.", il):
        return "Wounding", "Granatsplitter-Verwundung"
    if re.search(r"schußverl\.|schussverl\.", il):
        return "Wounding", "Schussverwundung"
    if re.search(r"verl\.|verwund", il):
        return "Wounding", None
    if re.search(r"lazarett|laz\.|k\.laz\.|res\.laz\.|feldlaz", il):
        return "Hospitalization", None
    if re.search(r"entl\.|entlass", il):
        return "Discharge", None
    if re.search(r"verm\.|vermisst", il):
        return "Missing", None
    return "Unknown", None


# ─── 4. extract_wast ─────────────────────────────────────────────────────────

def extract_wast(pdf_path: str | Path) -> dict:
    """Extrahiert strukturierte Daten aus einer WASt-Karteikarte via Claude Vision.

    Gibt zurück:
    {
        "pages": [{"card_type", "familienname", "vorname", "geboren_am",
                   "meldungen": [{"datum", "datum_iso", "datum_precision",
                                  "ort", "einheit", "inhalt_original"}]}],
        "source": {"type": "wast", "certainty": 5, "generated_by": "direkt", "reference": "..."},
    }
    """
    pdf_path = Path(pdf_path)
    doc = fitz.open(str(pdf_path))
    total = len(doc)
    doc.close()

    # Namenshinweis aus Dateiname für Vorderseite ("Koppermann, Hans-Jürgen_B 563-1 ...")
    stem = pdf_path.stem
    _name_part = stem.split("_")[0].strip()
    _name_hint = (
        f"\n\nWichtig: Laut Dateiname gehört diese Karte zu »{_name_part}«. "
        "Lies Familienname und Vorname besonders sorgfältig und gleiche sie mit diesem Hinweis ab."
        if ("," in _name_part) else ""
    )

    pages = []
    for i in range(total):
        if i == 0:
            ptype = "karte_I_vorderseite"
        elif i == 1:
            ptype = "karte_I_rueckseite"
        else:
            ptype = "karte_II"

        prompt = _WAST_PROMPTS[ptype] + (_name_hint if i == 0 else "")
        b64 = pdf_page_to_base64(pdf_path, i)
        data = _call_vision(b64, prompt)

        # Geburtsdatum normalisieren → ISO
        raw_bdate = data.get("geboren_am")
        if raw_bdate and raw_bdate != "null":
            iso, _ = _parse_date_partial(raw_bdate)
            data["geboren_am"] = iso or raw_bdate
        else:
            data["geboren_am"] = None

        # Meldungs-Datum normalisieren + Abkürzungen auflösen
        for m in data.get("meldungen", []):
            raw = m.get("datum")
            if raw and raw != "null":
                iso, prec = _parse_date_partial(raw)
            else:
                iso, prec = None, "unknown"
            m["datum_iso"] = iso
            m["ereignis_datum"] = iso   # Alias für Qualitätschecks
            m["datum_precision"] = prec

            r = resolve_abbreviations(m.get("inhalt_original", ""))
            m["abbrev"] = r["found"]
            m["_abbrev_unresolved"] = r["unresolved"]

        pages.append(data)

    # Nicht aufgelöste Abkürzungen aus allen Seiten aggregieren
    unresolved: set[str] = set()
    for page in pages:
        for m in page.get("meldungen", []):
            unresolved.update(m.pop("_abbrev_unresolved", []))

    ref = stem.split("_", 1)[1].replace("_", " / ") if "_" in stem else stem

    return {
        "pages": pages,
        "source": {
            "type": "wast",
            "certainty": 5,
            "generated_by": "direkt",
            "reference": ref,
        },
        "unresolved_abbreviations": sorted(unresolved),
    }


# ─── 5. ingest_wast ──────────────────────────────────────────────────────────

def ingest_wast(pdf_path: str | Path) -> list[str]:
    """Lädt WASt-Karteikarte in familiengeschichte.db.

    - Actor anlegen falls nicht vorhanden
    - Pro klassifizierbarer Meldung: Event (Wounding/Hospitalization/Discharge/Missing)
      + Participation (role=patient), certainty=5
    """
    data = extract_wast(pdf_path)
    today = date.today().isoformat()

    # Person aus Karte I Vorderseite
    vorderseite = next(
        (p for p in data["pages"] if p.get("card_type") == "karte_I_vorderseite"), {}
    )
    family = vorderseite.get("familienname") or ""
    given = vorderseite.get("vorname") or ""
    bdate = vorderseite.get("geboren_am")
    year = bdate[:4] if bdate and re.match(r"\d{4}", bdate) else None
    actor_id = _make_person_id(family, given, year) if (family and year) else None

    if actor_id:
        with db._get_conn() as conn:
            if not _actor_exists(conn, actor_id):
                db.insert_actor({
                    "id": actor_id,
                    "type": "Person",
                    "pref_label": f"{family}, {given}",
                    "alt_labels": [],
                    "family_name": family,
                    "given_name": given,
                    "birth_date": bdate,
                    "created_at": today,
                })

    actor_ids = [actor_id] if actor_id else []
    actor_short = actor_id.replace("person_", "") if actor_id else "unknown"

    # Meldungen aus allen Seiten sammeln
    events: list[dict] = []
    participations: list[dict] = []
    _id_seen: dict[str, int] = defaultdict(int)
    # Unknown-Meldungen mit ort-Angabe für nachträgliches Place-Enrichment
    _ort_by_date: dict[str, str] = {}

    for page in data["pages"]:
        for m in page.get("meldungen", []):
            inhalt = m.get("inhalt_original", "")
            etype, subtype = _classify_meldung(inhalt)
            if etype == "Unknown":
                # Ort für gleichdatierte Events merken
                raw_ort = m.get("ort")
                if raw_ort and raw_ort.strip().lower() not in ("", "null", "none"):
                    d_iso = m.get("datum_iso")
                    if d_iso and d_iso not in _ort_by_date:
                        _ort_by_date[d_iso] = raw_ort.strip()
                continue

            date_iso = m.get("datum_iso")
            precision = m.get("datum_precision", "unknown")

            # WASt-Karten enthalten Post-War-Bearbeitungsvermerke mit späten Daten
            # (z.B. "25.7.80" = WASt-Bearbeitungsdatum). Wenn das extrahierte Datum
            # nach Kriegsende liegt, Datum aus inhalt_original retten.
            if date_iso and date_iso > "1945-05-09":
                m_date = re.search(r'\b(\d{1,2}\.\d{1,2}\.\d{2,4})\b', inhalt)
                if m_date:
                    recovered, rec_prec = _parse_date_partial(m_date.group(1))
                    if recovered and recovered <= "1945-05-09":
                        date_iso, precision = recovered, rec_prec
                if date_iso > "1945-05-09":
                    continue  # Kein Kriegsdatum rekonstruierbar → Event überspringen

            date_slug = date_iso.replace("-", "_") if date_iso else "unbekannt"

            base_id = f"event_wast_{actor_short}_{etype.lower()}_{date_slug}"
            _id_seen[base_id] += 1
            n = _id_seen[base_id]
            event_id = base_id if n == 1 else f"{base_id}_{n}"

            place = _extract_place_from_meldung(inhalt, m.get("ort"))

            event: dict = {
                "id": event_id,
                "type": etype,
                "subtype": subtype,
                "label": f"{family}, {given}: {inhalt[:80]}",
                "time_span": {
                    "begin": date_iso,
                    "end": date_iso,
                    "precision": precision,
                },
                "source": {
                    "type": "wast",
                    "reference": data["source"]["reference"],
                    "certainty": 5,
                    "generated_by": "direkt",
                },
                "created_at": today,
            }
            if place:
                event["place"] = place
            events.append(event)

            if actor_id:
                participations.append({
                    "event_id": event_id,
                    "actor_id": actor_id,
                    "relation": "had_participant",
                    "role": "patient",
                    "created_at": today,
                })

    # Enrichment: Unknown-Meldungen mit ort= auf gleichdatierte Events übertragen
    for event in events:
        if event.get("place") and event["place"].get("lat") is not None:
            continue  # bereits geortet
        date_key = event.get("time_span", {}).get("begin")
        fallback_ort = _ort_by_date.get(date_key)
        if fallback_ort:
            place = _extract_place_from_meldung("", fallback_ort)
            if place and place.get("lat") is not None:
                event["place"] = place

    _validate_and_commit(events, participations, str(pdf_path))
    return actor_ids
