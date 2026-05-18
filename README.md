# Abstract Searcher

Search a conference program PDF by name and export your sessions to calendar, spreadsheet, or plain text.

Tested for doctors attending KCR/ICR and GBCC, but extensible to other conferences.

---

## Features

- **Fuzzy name search** — finds "Sung Hwang", "Hwang Sung", "S Hwang" in any order
- **Role detection** — Chair, Speaker (primary author), Discussant
- **Four export formats**:
  - `.ics` — calendar with correct timezone (`VTIMEZONE`, imports correctly into phone/Outlook)
  - `.txt` — plain text for email (`*` speaker, `[Chair]` chair)
  - `.xlsx` — spreadsheet with date, time, room, role columns
  - `.html` — self-contained viewer with real-time search (no server needed)
- **Supported conferences**: KCR 2025, ICR 2026 (adapters for each PDF layout)

---

## Quick Start

```bash
pip install -r requirements.txt

# Search ICR 2026 for "Sung Hwang" — export all formats
python -m search.cli \
  --pdf "data/pdfs/EN-ICR 2026 f. prog_110526.pdf" \
  --name "Sung Hwang" \
  --ics  results/sung_hwang.ics \
  --text results/sung_hwang.txt \
  --xlsx results/sung_hwang.xlsx

# Search KCR 2025
python -m search.cli \
  --pdf "data/pdfs/KCR2025_Program_Book.pdf" \
  --name "Jin Mo Goo" \
  --ics  results/jin_mo_goo.ics \
  --text results/jin_mo_goo.txt \
  --xlsx results/jin_mo_goo.xlsx
```

---

## CLI Options

```
python -m search.cli
  --pdf <path>        PDF path (required)
  --name "<query>"    Name to search (required)
  --threshold 80      Fuzzy match threshold 0–100 (default 80)
  --save              Save all parsed sessions to data/sessions/<stem>.json
  --json              Print results as JSON
  --ics <path>        Export to .ics with VTIMEZONE (recommended)
  --text <path>       Export to plain text
  --xlsx <path>       Export to .xlsx spreadsheet
  --export-html <path>  Export search results to HTML table
  --export-ics <path>   Export to .ics UTC-only (legacy)
```

---

## Standalone HTML Viewer

Build a self-contained viewer from a full sessions JSON (real-time search, no server):

```bash
# Parse and save all sessions first
python -m search.cli --pdf data/pdfs/KCR2025_Program_Book.pdf --name . --save

# Build viewer
python -m exporters.html_exporter data/sessions/KCR2025_Program_Book.json viewer.html
```

Open `viewer.html` in any browser. Search by name, session code, room, or role.

---

## Output Examples

**Plain text (`--text`)**
```
ICR 2026 — Cartagena, Colombia (America/Bogota)
===============================================

* Thursday, May 14, 2026  14:00–14:20  Room Barahona 4
  AI and radiology: Turning crisis into opportunity for residency education

[Chair] Friday, September 26, 2025  12:20–13:20  Grand Ballroom 101-102
  [LS 09 - Optimizing CT Contrast Dosing with Innovative Technology]
```

**Calendar (`--ics`)**
- Imports into Google Calendar, Apple Calendar, Outlook
- Events show in the conference timezone (UTC-5 Bogotá → correct local time on Korean phone)
- Speaker summary: `★ AI and radiology: Turning crisis into opportunity`
- Chair summary: `[Chair] SS 12: Deep-Learning Application in Chest Radiograph`

**Spreadsheet (`--xlsx`)**

| Date | Day | Start | End | Room | Role | Primary Author | Session Code | Title |
|---|---|---|---|---|---|---|---|---|
| 2026-05-14 | Thursday | 14:00 | 14:20 | Room Barahona 4 | Speaker | Y | | AI and radiology… |
| 2025-09-25 | Thursday | 16:30 | 17:50 | Grand Ballroom 101 | Chair | N | SS 12 | Deep-Learning… |

---

## Project Structure

```
abstract-searcher/
├── adapters/
│   ├── icr.py          ICR 2026 PDF layout parser
│   ├── kcr.py          KCR 2025 PDF layout parser
│   └── generic.py      Fallback parser
├── exporters/
│   ├── ics_exporter.py  RFC 5545 ICS with VTIMEZONE
│   ├── text_exporter.py Plain text export
│   ├── xlsx_exporter.py Excel export (openpyxl)
│   └── html_exporter.py Standalone HTML viewer
├── search/
│   ├── cli.py          CLI entry point
│   └── matcher.py      Fuzzy name matching (rapidfuzz)
├── data/
│   ├── pdfs/           Input PDFs (not tracked in git)
│   └── sessions/       Parsed session JSON + viewer HTML
├── main.py             Adapter auto-detection + search_pdf()
└── requirements.txt
```

---

## Requirements

```
pymupdf>=1.24.0
ics>=0.7
rapidfuzz>=3.0
openpyxl>=3.0
```

Install: `pip install -r requirements.txt`

---

## Adding a New Conference

1. Create `adapters/<conf>.py` with a `parse(pdf_path) -> list[dict]` function and an `EVENT_META` dict
2. Add timezone to `_VTIMEZONE` in `exporters/ics_exporter.py` if not already present
3. Register the adapter in `main._detect_adapter()`

Each record returned by `parse()` must have these fields:

```python
{
    "page": int,
    "date": str,          # "Sep. 26 (Fri)" or "Thursday, May 14th"
    "time": str,          # "14:00-14:20"
    "room": str,
    "session_code": str,
    "session_title": str,
    "role": str,          # "chair" | "speaker" | "discussant"
    "is_primary_author": bool,
    "person": str,
    "affiliation": str,
    "talk_title": str,
}
```
