"""Export sessions to a plain-text file suitable for email."""
from __future__ import annotations

import datetime
import re
import textwrap
from pathlib import Path
from typing import Any

_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _extract_year(event_name: str) -> int | None:
    m = re.search(r"\b(20\d{2})\b", event_name or "")
    return int(m.group(1)) if m else None


def _parse_date(date_str: str, year: int) -> tuple[int, int, int] | None:
    m = re.search(r"([A-Za-z]+)\.?\s+(\d{1,2})", date_str or "")
    if not m:
        return None
    key = m.group(1).lower()[:3]
    mo = _MONTH_MAP.get(key)
    return (year, mo, int(m.group(2))) if mo else None


def _parse_time(time_str: str) -> tuple[tuple[int, int], tuple[int, int]] | None:
    m = re.match(r"(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})", (time_str or "").strip())
    return ((int(m.group(1)), int(m.group(2))), (int(m.group(3)), int(m.group(4)))) if m else None


def _format_date(ymd: tuple[int, int, int]) -> str:
    y, mo, d = ymd
    dt = datetime.date(y, mo, d)
    return f"{_DAY_NAMES[dt.weekday()]}, {_MONTH_NAMES[mo]} {d}, {y}"


def _sort_key(s: dict, year: int | None) -> tuple:
    ymd = _parse_date(s.get("date", ""), year) if year else None
    times = _parse_time(s.get("time", ""))
    return (
        ymd[1] if ymd else 99,
        ymd[2] if ymd else 99,
        times[0][0] if times else 99,
        times[0][1] if times else 99,
    )


def export_text(
    sessions: list[dict[str, Any]],
    event_timezone: str,
    output_path: str | Path,
    event_name: str = "",
    event_location: str = "",
) -> None:
    year = _extract_year(event_name)
    sorted_sessions = sorted(sessions, key=lambda s: _sort_key(s, year))

    out: list[str] = []

    header = event_name or "Conference Program"
    meta_parts = [p for p in [event_location, f"({event_timezone})" if event_timezone else ""] if p]
    if meta_parts:
        header += f" — {' '.join(meta_parts)}"
    out.append(header)
    out.append("=" * min(len(header), 80))
    out.append("")

    for s in sorted_sessions:
        role = (s.get("role") or "unknown").lower()
        is_primary = bool(s.get("is_primary_author"))
        talk_title = s.get("talk_title") or ""
        session_code = s.get("session_code") or ""
        session_title = s.get("session_title") or ""
        room = s.get("room") or ""

        ymd = _parse_date(s.get("date", ""), year) if year else None
        times = _parse_time(s.get("time", ""))

        date_str = _format_date(ymd) if ymd else (s.get("date") or "")
        if times:
            (sh, sm), (eh, em) = times
            time_str = f"{sh:02d}:{sm:02d}–{eh:02d}:{em:02d}"
        else:
            time_str = s.get("time") or ""

        if is_primary:
            prefix = "* "
        elif role in ("chair", "discussant"):
            prefix = f"[{role.capitalize()}] "
        else:
            prefix = "  "

        parts = [p for p in [date_str, time_str, room] if p]
        out.append(prefix + "  ".join(parts))

        if talk_title:
            out.append(textwrap.fill(talk_title, width=80,
                                     initial_indent="  ", subsequent_indent="  "))

        sess_parts = [p for p in [session_code, session_title] if p]
        if sess_parts:
            out.append(f"  [{' - '.join(sess_parts)}]")

        out.append("")

    Path(output_path).write_text("\n".join(out), encoding="utf-8")
