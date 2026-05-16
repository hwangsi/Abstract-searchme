"""Generic adapter: detects session blocks from a flat line list.

Anchors used to detect a new session boundary:
  1. Time pattern  HH:MM  (or HH:MM-HH:MM, AM/PM variants)
  2. Session code  e.g. S-01, SS01, OP-1, 구연-1  (capital letter + digits)
  3. Blank-line gap between blocks (carried as sentinel lines by the parser)

Output: list of session dicts with keys
  { page, time, code, title, body }
"""

import re
from pathlib import Path
from typing import Any

from parsers.pdf_parser import extract_lines

# ── patterns ──────────────────────────────────────────────────────────────────

_TIME_RE = re.compile(
    r"\b"
    r"(\d{1,2}:\d{2})"        # HH:MM
    r"(?:\s*[-~–]\s*\d{1,2}:\d{2})?"  # optional -HH:MM
    r"(?:\s*(?:AM|PM|am|pm))?"
    r"\b"
)

_CODE_RE = re.compile(
    r"(?:^|\s)"
    r"([A-Z가-힣]{1,4}[-\s]?\d{1,4}[A-Z]?)"   # S-01, SS01, OP1, 구연-1 …
    r"(?:\s|$)"
)


def _is_anchor(text: str) -> bool:
    return bool(_TIME_RE.search(text) or _CODE_RE.search(text))


# ── public API ─────────────────────────────────────────────────────────────────

def parse(pdf_path: str | Path) -> list[dict[str, Any]]:
    """Parse *pdf_path* and return a list of normalised session dicts."""
    lines = extract_lines(pdf_path)
    sessions: list[dict] = []
    current: dict | None = None

    for line in lines:
        text = line["text"]

        if _is_anchor(text):
            if current is not None:
                sessions.append(_finalise(current))
            current = {
                "page": line["page"],
                "time": _extract_time(text),
                "code": _extract_code(text),
                "title": text,
                "body_lines": [],
            }
        else:
            if current is not None:
                current["body_lines"].append(text)

    if current is not None:
        sessions.append(_finalise(current))

    return sessions


def _finalise(s: dict) -> dict:
    return {
        "page": s["page"],
        "time": s["time"],
        "code": s["code"],
        "title": s["title"],
        "body": "\n".join(s["body_lines"]),
    }


def _extract_time(text: str) -> str:
    m = _TIME_RE.search(text)
    return m.group(0).strip() if m else ""


def _extract_code(text: str) -> str:
    m = _CODE_RE.search(text)
    return m.group(1).strip() if m else ""
