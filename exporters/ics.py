"""Export search results to an .ics calendar file."""

from __future__ import annotations
import re
from pathlib import Path
from typing import Any

from ics import Calendar, Event as IcsEvent

_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10,
    "nov": 11, "dec": 12,
}


def _extract_year(event_name: str) -> "int | None":
    m = re.search(r"\b(20\d{2})\b", event_name)
    return int(m.group(1)) if m else None


def _parse_date(date_str: str, year: int) -> "tuple[int, int, int] | None":
    """'Sep. 26 (Fri)' → (2025, 9, 26)"""
    m = re.search(r"([A-Za-z]+)\.?\s+(\d{1,2})", date_str)
    if not m:
        return None
    key = m.group(1).lower()[:3]
    month = _MONTH_MAP.get(key)
    if not month:
        return None
    return year, month, int(m.group(2))


def _parse_time(time_str: str) -> "tuple[tuple[int, int], tuple[int, int]] | None":
    """'12:20-13:20' → ((12, 20), (13, 20))"""
    m = re.match(r"(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})", time_str.strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2))), (int(m.group(3)), int(m.group(4)))


def export(
    hits: list[dict[str, Any]],
    output_path: "Path | str",
    event_meta: "dict[str, Any] | None" = None,
    query: str = "",
) -> None:
    event_meta = event_meta or {}
    tz_name = event_meta.get("event_timezone", "UTC")
    event_name = event_meta.get("event_name", "")
    year = _extract_year(event_name)

    import arrow
    tz_info = arrow.now(tz_name).tzinfo

    cal = Calendar()

    for h in hits:
        e = IcsEvent()

        role = h.get("role", "unknown")
        talk = h.get("talk_title") or h.get("session_title") or ""
        e.name = f"[{role.upper()}] {talk}" if talk else f"[{role.upper()}]"
        e.location = h.get("room") or ""

        desc_parts = []
        if h.get("person"):
            desc_parts.append(h["person"])
        if h.get("affiliation"):
            desc_parts.append(h["affiliation"])
        session = " - ".join(filter(None, [h.get("session_code"), h.get("session_title")]))
        if session:
            desc_parts.append(f"Session: {session}")
        if query:
            desc_parts.append(f"Query: {query}")
        e.description = "\n".join(desc_parts)

        ymd = _parse_date(h.get("date", ""), year) if year and h.get("date") else None
        times = _parse_time(h.get("time", "")) if h.get("time") else None

        if ymd and times:
            (sh, sm), (eh, em) = times
            e.begin = arrow.Arrow(*ymd, sh, sm, 0).replace(tzinfo=tz_info)
            e.end = arrow.Arrow(*ymd, eh, em, 0).replace(tzinfo=tz_info)

        cal.events.add(e)

    Path(output_path).write_text(cal.serialize(), encoding="utf-8")
