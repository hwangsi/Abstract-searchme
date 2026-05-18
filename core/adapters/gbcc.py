"""GBCC (Global Breast Cancer Conference) abstract book adapter.

Two record sources parsed from the PDF:

  1. Program pages  — lines with Speaker / Presenter / Moderator / Chair labels
     Each entry:  role  |  name  |  abstract_ref_page  |  talk_title  |  affiliation

  2. Index pages   — abstract code blocks (PO/MO/OS/SS/IS/YI + digits)
     Each entry:  code  |  title  |  internal_page  |  comma-separated authors
     One record per author; is_primary_author=True only for the first.

Abstract body pages (Background/Methods/Results/...) are skipped; they
duplicate the index data and contain References sections that would
produce false-positive person matches.
"""

from __future__ import annotations

import re
from pathlib import Path
import fitz

EVENT_META = {
    "event_name": "GBCC 2026",
    "event_location": "Seoul, Korea",
    "event_timezone": "Asia/Seoul",
}

# ── patterns ─────────────────────────────────────────────────────────────────

_TIME_RE     = re.compile(r'^(\d{1,2}:\d{2}-\d{1,2}:\d{2})')
_DATE_RE     = re.compile(r'((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}\s*\([A-Za-z]+\))', re.I)
_ROLE_SOLO   = re.compile(r'^(Speaker|Presenter|Moderator|Chair|Co-chair|Discussant)\s*$', re.I)
_ROLE_INLINE = re.compile(r'^(Moderator|Chair|Co-chair|Discussant)\s{2,}(.+)', re.I)
_CODE_RE     = re.compile(r'^(PO|MO|OS|SS|IS|YI|OP)\d{3,}$', re.I)
_PAGE_ONLY   = re.compile(r'^\d{2,4}$')
_REF_HDR_RE  = re.compile(r'^References?\s*$', re.I)
# Section-header strings that mark the end of an author block on index pages
_INDEX_SKIP  = frozenset({
    'Poster Presentation', 'Mini Oral Presentation', 'Oral Presentation',
    'Special Session', 'Symposium', 'Global Breast Cancer Conference 2026',
    'Program Details', 'Invited Symposium', 'Educational Session',
    'Invited Lecture', 'Panel Discussion', 'Opening Ceremony',
})

ROLE_MAP = {
    'speaker':    'speaker',
    'presenter':  'speaker',
    'moderator':  'chair',
    'chair':      'chair',
    'co-chair':   'chair',
    'discussant': 'discussant',
}


# ── text cleaning ─────────────────────────────────────────────────────────────

def _clean(s: str) -> str:
    """Replace tab with space, remove remaining control chars, strip leading ? bullet."""
    s = s.replace('\t', ' ')
    s = re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', s)
    return s.strip().lstrip('�‌​﻿?').strip()


def _looks_like_affil(s: str) -> bool:
    """True if the line looks like an institution/affiliation rather than a title."""
    if re.search(r'\b(Univ|Hospital|Institute|Medical|Center|College|School|Dept|Cancer|Clinic)\b', s, re.I):
        return True
    # Ends with ", Country" pattern
    if re.search(r',\s*[A-Z][a-zA-Z .\-]{2,25}\s*$', s):
        return True
    return False


def _split_authors(raw: str) -> list[str]:
    """Split 'A1, B2, C3' author line, stripping trailing superscript digits."""
    parts = [p.strip() for p in raw.split(',')]
    result = []
    for p in parts:
        name = re.sub(r'\d+$', '', p).strip()
        if len(name.split()) >= 2:
            result.append(name)
    return result


# ── record factory ────────────────────────────────────────────────────────────

def _make_rec(
    *, page: int, date: str, time: str, room: str,
    session_title: str, role: str, is_primary: bool,
    person: str, affiliation: str, talk_title: str,
    session_code: str = '',
) -> dict:
    return {
        'page':             page,
        'date':             date,
        'time':             time,
        'room':             room,
        'session_code':     session_code,
        'session_title':    session_title,
        'role':             role,
        'is_primary_author': is_primary,
        'person':           person,
        'affiliation':      affiliation,
        'talk_title':       talk_title,
    }


# ── per-page parsers ──────────────────────────────────────────────────────────

def _parse_program_page(lines: list[str], records: list[dict]) -> None:
    """Extract Speaker/Presenter/Moderator/Chair entries from schedule pages."""
    date = time_str = room = session_title = ''
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # Date context
        dm = _DATE_RE.search(line)
        if dm:
            date = dm.group(1)
            i += 1
            continue

        # Time → new session context
        tm = _TIME_RE.match(line)
        if tm:
            time_str = tm.group(1)
            # look ahead: [session-type] [RM ...] [session-title]
            j = i + 1
            if j < n and not _ROLE_SOLO.match(lines[j]) and not _ROLE_INLINE.match(lines[j]):
                j += 1  # skip session-type line
            if j < n and lines[j].startswith('RM '):
                room = lines[j]
                j += 1
            if j < n and not _ROLE_SOLO.match(lines[j]) and not _ROLE_INLINE.match(lines[j]) and not _TIME_RE.match(lines[j]):
                session_title = lines[j]
            i += 1
            continue

        # Inline role: "Moderator  Name" (tab converted to spaces)
        mi = _ROLE_INLINE.match(line)
        if mi:
            role_raw = mi.group(1).lower()
            name = mi.group(2).strip()
            i += 1
            affil = ''
            if i < n and _looks_like_affil(lines[i]):
                affil = lines[i]
                i += 1
            if len(name.split()) >= 2:
                records.append(_make_rec(
                    page=0, date=date, time=time_str, room=room,
                    session_title=session_title,
                    role=ROLE_MAP.get(role_raw, 'chair'),
                    is_primary=False, person=name, affiliation=affil, talk_title='',
                ))
            continue

        # Solo role on its own line: Speaker / Presenter
        ms = _ROLE_SOLO.match(line)
        if ms:
            role_raw = ms.group(1).lower()
            role = ROLE_MAP.get(role_raw, 'speaker')
            i += 1
            if i >= n:
                break

            name = lines[i].strip()
            i += 1

            # Optional abstract reference page number
            ref_page = 0
            if i < n and _PAGE_ONLY.match(lines[i]):
                try:
                    ref_page = int(lines[i])
                except ValueError:
                    pass
                i += 1

            # Accumulate title lines until an affiliation, role, or time line
            title_parts: list[str] = []
            while i < n:
                c = lines[i]
                if (
                    _looks_like_affil(c)
                    or _ROLE_SOLO.match(c)
                    or _ROLE_INLINE.match(c)
                    or _TIME_RE.match(c)
                    or _DATE_RE.search(c)
                ):
                    break
                title_parts.append(c)
                i += 1
            title = ' '.join(title_parts)

            # Optional affiliation
            affil = ''
            if i < n and _looks_like_affil(lines[i]):
                affil = lines[i]
                i += 1

            if len(name.split()) >= 2:
                records.append(_make_rec(
                    page=ref_page, date=date, time=time_str, room=room,
                    session_title=session_title, role=role,
                    is_primary=True, person=name, affiliation=affil, talk_title=title,
                ))
            continue

        i += 1


def _parse_index_page(lines: list[str], records: list[dict]) -> None:
    """Extract abstract code blocks from PO/MO/OS/SS index pages."""
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        if not _CODE_RE.match(line):
            i += 1
            continue

        code = line
        i += 1

        # Collect title lines until a page-ref number, next code, or References
        title_parts: list[str] = []
        while i < n:
            c = lines[i]
            if _PAGE_ONLY.match(c) or _CODE_RE.match(c) or _REF_HDR_RE.match(c):
                break
            title_parts.append(c)
            i += 1

        # Page reference number
        page_ref = 0
        if i < n and _PAGE_ONLY.match(lines[i]):
            try:
                page_ref = int(lines[i])
            except ValueError:
                pass
            i += 1

        if not page_ref:
            continue  # malformed entry (e.g. abstract body page with no ref)

        # Collect author lines until next code, References, or section header.
        # Also stop on Author-Index format lines ("Surname, Firstname") which appear
        # in the back-of-book author index (e.g. "Moon, Woo Kyung") to prevent
        # those entries from being confused with co-author lists.
        author_parts: list[str] = []
        while i < n:
            c = lines[i]
            if _CODE_RE.match(c) or _REF_HDR_RE.match(c):
                break
            if c in _INDEX_SKIP:
                i += 1
                continue
            if re.match(r'^\(\d+\)$', c):  # page-number header like "(39)"
                break
            if re.match(r'^[A-Z][a-zA-Z-]+,\s', c):  # Author-Index: "Surname, Firstname"
                break
            author_parts.append(c)
            i += 1

        title = ' '.join(title_parts)
        author_raw = ' '.join(author_parts)

        authors = _split_authors(author_raw)
        if not authors:
            continue

        for idx, author in enumerate(authors):
            records.append(_make_rec(
                page=page_ref, date='', time='', room='',
                session_title='', role='speaker',
                is_primary=(idx == 0), person=author, affiliation='',
                talk_title=title, session_code=code,
            ))


# ── main entry point ──────────────────────────────────────────────────────────

def parse(pdf_path: str | Path) -> list[dict]:
    doc = fitz.open(str(pdf_path))
    records: list[dict] = []

    for pn in range(doc.page_count):
        raw_lines = doc[pn].get_text().splitlines()
        lines = [_clean(l) for l in raw_lines]
        lines = [l for l in lines if l]  # drop blank lines after cleaning

        has_code = any(_CODE_RE.match(l) for l in lines)
        has_role = any(_ROLE_SOLO.match(l) or _ROLE_INLINE.match(l) for l in lines)

        if has_code:
            _parse_index_page(lines, records)
        elif has_role:
            _parse_program_page(lines, records)
        # abstract body pages (Background/Methods/...) → skipped

    doc.close()
    return records
