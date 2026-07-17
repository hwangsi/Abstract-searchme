# Abstract Searcher v0.5.5

Conference program PDF searcher with a PySide6 desktop GUI and CLI.  
Search sessions by **name** or **affiliation**, export to calendar / spreadsheet / text / HTML.

Tested for physicians attending KCR, ICR, and GBCC — extensible to other conferences.
Also available as a web service with push reminders: see `docs/WEB_SERVICE_DESIGN.md` and `docs/WEB_DEV.md`.

---

## Supported Conferences

| Conference | PDF | Roles parsed |
|---|---|---|
| KCR 2025 | `KCR2025_Program_Book.pdf` | Chair, Speaker (primary + co-authors), Discussant |
| ICR 2026 | `EN-ICR 2026 f. prog_110526.pdf` | Chair, Speaker (primary + co-authors) |
| GBCC 2026 | `GBCC 2026_AbstractBook.pdf` | Chair, Speaker, Discussant, Panelist, Moderator |

---

## Desktop App (recommended)

### Pre-built binary

Download `AbstractSearcher.exe` from `dist/` and run it — no Python required.

### Run from source

```bash
pip install -r requirements.txt
python -m desktop.main
```

### Workflow

1. **Window 1 – Upload**: drag-and-drop (or browse) a conference PDF → parse
2. **Window 2 – Search**:
   - **Name search** — fuzzy match across all persons (chair / speaker / co-author)
   - **Affiliation search** — find everyone from a hospital or university
   - **Sort** results by role / time / abstract page
3. **Export** any result set to `.ics` / `.xlsx` / `.txt` (buttons in the toolbar)

---

## CLI

```bash
pip install -r requirements.txt

# Name search — ICR 2026
python -m cli.main \
  --pdf "data/pdfs/EN-ICR 2026 f. prog_110526.pdf" \
  --name "Sung Hwang" \
  --ics  results/sung_hwang.ics \
  --text results/sung_hwang.txt \
  --xlsx results/sung_hwang.xlsx

# Affiliation search — KCR 2025
python -m cli.main \
  --pdf "data/pdfs/KCR2025_Program_Book.pdf" \
  --affiliation "Seoul National University Bundang" \
  --xlsx results/bundang.xlsx
```

### CLI Options

```
--pdf <path>              PDF path (required)
--name "<query>"          Fuzzy name search
--affiliation "<query>"   Affiliation search (token-AND match)
--threshold 80            Fuzzy threshold 0–100 (default 80, name only)
--ics <path>              Export to .ics (VTIMEZONE, imports into phone/Outlook)
--text <path>             Export to plain text
--xlsx <path>             Export to .xlsx spreadsheet
--export-html <path>      Export to standalone HTML viewer
--json                    Print results as JSON
--save                    Save parsed sessions to data/sessions/<stem>.json
```

---

## Export Formats

**Calendar (`.ics`)**
- Imports into Google Calendar, Apple Calendar, Outlook
- Correct timezone per conference (Asia/Seoul, America/Bogota, …)
- Speaker: `★ AI and Radiology: Turning Crisis into Opportunity`
- Chair: `[Chair] SS 12: Deep-Learning Application in Chest Radiograph`

**Spreadsheet (`.xlsx`)**

| Date | Day | Start | End | Room | Role | Primary | Session | Title |
|---|---|---|---|---|---|---|---|---|
| 2026-05-14 | Thursday | 14:00 | 14:20 | Barahona 4 | Speaker | Y | | AI and radiology… |

**Plain text (`.txt`)**
```
ICR 2026 — Cartagena, Colombia (America/Bogota)

* Thursday, May 14, 2026  14:00–14:20  Room Barahona 4
  AI and radiology: Turning crisis into opportunity for residency education

[Chair] Friday, Sep 26, 2025  12:20–13:20  Grand Ballroom 101-102
  [SS 09 – Optimizing CT Contrast Dosing]
```

---

## Project Structure

```
abstract-searcher/
├── core/
│   ├── adapters/
│   │   ├── __init__.py     load_pdf() — detect adapter + normalize
│   │   ├── affil_refs.py   superscript ref parsing (¹²³ → per-author affil)
│   │   ├── post.py         normalize_records() — dedup + invariant enforce
│   │   ├── icr.py          ICR 2026 parser
│   │   ├── kcr.py          KCR 2025 parser
│   │   ├── gbcc.py         GBCC 2026 parser
│   │   └── generic.py      fallback parser
│   ├── exporters/
│   │   ├── ics_exporter.py  RFC 5545 ICS with VTIMEZONE
│   │   ├── text_exporter.py plain text
│   │   ├── xlsx_exporter.py Excel (openpyxl)
│   │   └── html_exporter.py standalone HTML viewer
│   └── search/
│       └── matcher.py      fuzzy name + affiliation matching (rapidfuzz)
├── desktop/
│   ├── main.py             app entry point
│   └── windows/
│       ├── upload_window.py  Window 1 — PDF upload + parse
│       └── search_window.py  Window 2 — search + results + export
├── cli/
│   └── main.py             CLI entry point
├── tests/
│   └── test_ground_truth.py  17 regression tests
├── build/
│   └── abstract_searcher.spec  PyInstaller onefile spec
├── data/pdfs/              input PDFs (not tracked in git)
├── pyproject.toml
└── requirements.txt
```

---

## Requirements

```
pymupdf>=1.24.0
ics>=0.7
rapidfuzz>=3.0
openpyxl>=3.0
PySide6>=6.6      # desktop app only
```

Install: `pip install -r requirements.txt`

---

## Adding a New Conference

1. Create `core/adapters/<conf>.py` with `parse(pdf_path) -> list[dict]` and `EVENT_META`
2. Register in `core/adapters/__init__.py` (`_detect_adapter`)
3. Add timezone to `_VTIMEZONE` in `core/exporters/ics_exporter.py` if needed

Each record must include:

```python
{
    "page": int,
    "date": str,           # "Sep. 26 (Fri)"
    "time": str,           # "14:00-14:20"
    "room": str,
    "session_code": str,
    "session_title": str,
    "role": str,           # "chair" | "speaker" | "discussant"
    "is_primary_author": bool,
    "person": str,
    "affiliation": str,
    "talk_title": str,
    "authors_all": list[str],   # all authors for this talk
}
```

---

## Running Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

17 ground truth tests cover name search, affiliation search, co-author mapping, per-author superscript affiliation, and record invariants across all three adapters.

---

## Changelog

| Version | Description |
|---|---|
| v0.5.5 | UI: larger font (15pt cards, 18pt base), filled radio buttons, sort by role/time/page, export buttons in toolbar |
| v0.5.4 | KCR: new talk code formats (IDP/JS/KSR/SE) + author heuristic guards → Bundang Hospital search 10→57 hits |
| v0.5.3 | KCR: superscript-based per-author affiliation mapping (¹²³) |
| v0.5.2 | KCR: co-author emit + normalize_records() dedup/invariant enforcement |
| v0.5.1 | PyInstaller onefile exe + error logging (windowed mode) |
| v0.5.0 | Affiliation search mode; GBCC 2026 adapter; AND-token matching |
| v0.4.0 | PySide6 desktop GUI: Window 1 (upload) + Window 2 (search + export) |
| v0.3.0 | Monorepo refactor (core / cli / desktop) |
| v0.2.0 | ICR 2026 adapter; multi-format export (.ics / .xlsx / .txt / .html) |
| v0.1.0 | Initial release: KCR 2025 parser + fuzzy name search |
