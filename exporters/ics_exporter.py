"""
Export sessions to an .ics calendar file with VTIMEZONE blocks.

ics 0.7.3 converts all datetimes to UTC and never emits VTIMEZONE components.
We generate RFC 5545-compliant iCalendar text directly so calendar apps can
display the event in the original conference timezone and convert correctly to
the attendee's local time (e.g. UTC-5 Bogotá → +14 h on a Korean device).

arrow is used for datetime arithmetic; it is installed as a dependency of ics.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

import arrow  # installed as a dependency of the ics package

# ── VTIMEZONE blocks (CRLF line endings, no trailing newline) ────────────────
# Hardcoded for the two conference timezones used by KCR (Seoul) and ICR
# (Bogotá). Neither observes DST so a STANDARD-only block suffices.
# Add entries here for new venues.

_VTIMEZONE: dict[str, str] = {
    "Asia/Seoul": (
        "BEGIN:VTIMEZONE\r\n"
        "TZID:Asia/Seoul\r\n"
        "BEGIN:STANDARD\r\n"
        "DTSTART:19700101T000000\r\n"
        "TZOFFSETFROM:+0900\r\n"
        "TZOFFSETTO:+0900\r\n"
        "TZNAME:KST\r\n"
        "END:STANDARD\r\n"
        "END:VTIMEZONE\r\n"
    ),
    "America/Bogota": (
        "BEGIN:VTIMEZONE\r\n"
        "TZID:America/Bogota\r\n"
        "BEGIN:STANDARD\r\n"
        "DTSTART:19700101T000000\r\n"
        "TZOFFSETFROM:-0500\r\n"
        "TZOFFSETTO:-0500\r\n"
        "TZNAME:COT\r\n"
        "END:STANDARD\r\n"
        "END:VTIMEZONE\r\n"
    ),
}

# UTC offset in minutes — used when timezone is not in _VTIMEZONE
_TZ_OFFSET_MIN: dict[str, int] = {
    "Asia/Seoul": 540, "Asia/Tokyo": 540, "Asia/Shanghai": 480,
    "America/Bogota": -300, "America/New_York": -300,
    "America/Chicago": -360, "America/Los_Angeles": -480,
    "Europe/London": 0, "Europe/Paris": 60, "Europe/Berlin": 60,
    "UTC": 0,
}

_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


# ── Datetime helpers ──────────────────────────────────────────────────────────

def _extract_year(event_name: str) -> int | None:
    m = re.search(r"\b(20\d{2})\b", event_name or "")
    return int(m.group(1)) if m else None


def _parse_date(date_str: str, year: int) -> tuple[int, int, int] | None:
    """'Sep. 26 (Fri)' or 'Thursday, May 14th' → (year, month, day)."""
    m = re.search(r"([A-Za-z]+)\.?\s+(\d{1,2})", date_str or "")
    if not m:
        return None
    key = m.group(1).lower()[:3]
    month = _MONTH_MAP.get(key)
    return (year, month, int(m.group(2))) if month else None


def _parse_time(time_str: str) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """'12:20-13:20' → ((12, 20), (13, 20))."""
    m = re.match(r"(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})", (time_str or "").strip())
    return ((int(m.group(1)), int(m.group(2))), (int(m.group(3)), int(m.group(4)))) if m else None


def _to_utc_str(y: int, mo: int, d: int, h: int, mi: int, offset_min: int) -> str:
    """Fallback for unknown tz: shift local time to UTC using static offset."""
    utc = arrow.Arrow(y, mo, d, h, mi).shift(minutes=-offset_min)
    return utc.format("YYYYMMDDTHHmmss") + "Z"


# ── ICS text helpers ──────────────────────────────────────────────────────────

def _ics_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold_prop(name: str, value: str, params: str = "") -> str:
    """Format an ICS property, folded at 75 UTF-8 bytes per RFC 5545 §3.1."""
    prefix = f"{name};{params}" if params else name
    line = f"{prefix}:{value}"
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line + "\r\n"
    parts: list[str] = []
    while len(encoded) > 75:
        end = 75
        while end > 0 and (encoded[end] & 0xC0) == 0x80:
            end -= 1  # back up to UTF-8 character boundary
        parts.append(encoded[:end].decode("utf-8"))
        encoded = b" " + encoded[end:]  # continuation line starts with SPACE
    parts.append(encoded.decode("utf-8"))
    return "\r\n".join(parts) + "\r\n"


# ── SUMMARY / DESCRIPTION ─────────────────────────────────────────────────────

def _build_summary(session: dict[str, Any]) -> str:
    """
    ★ {talk_title}          — is_primary_author=True (speaker)
    [{Role}] {code}: {title} — chair / discussant
    """
    if session.get("is_primary_author") and session.get("talk_title"):
        return f"★ {session['talk_title']}"
    role = (session.get("role") or "unknown").capitalize()
    parts = list(filter(None, [session.get("session_code"), session.get("session_title")]))
    title = ": ".join(parts) if parts else (session.get("talk_title") or "")
    return f"[{role}] {title}" if title else f"[{role}]"


def _build_description(session: dict[str, Any], event_name: str) -> str:
    lines: list[str] = []
    if session.get("person"):
        lines.append(session["person"])
    if session.get("affiliation"):
        lines.append(session["affiliation"])
    sess = " - ".join(filter(None, [session.get("session_code"), session.get("session_title")]))
    if sess:
        lines.append(f"Session: {sess}")
    if session.get("role"):
        lines.append(f"Role: {session['role']}")
    if event_name:
        lines.append(f"Event: {event_name}")
    return "\\n".join(_ics_escape(ln) for ln in lines)


# ── Public API ────────────────────────────────────────────────────────────────

def export_ics(
    sessions: list[dict[str, Any]],
    event_timezone: str,
    output_path: str | Path,
    event_name: str = "",
) -> None:
    """Write sessions to an RFC 5545 .ics file.

    When event_timezone is in _VTIMEZONE, the output includes:
      - A VTIMEZONE component
      - DTSTART/DTEND with TZID= in the original local time

    For unknown timezones, falls back to UTC (DTSTART:...Z).
    """
    tz = event_timezone or "UTC"
    year = _extract_year(event_name)
    has_vtimezone = tz in _VTIMEZONE
    tz_offset_min = _TZ_OFFSET_MIN.get(tz, 0)

    out = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//abstract-searcher//EN\r\n"
        "CALSCALE:GREGORIAN\r\n"
    )
    if has_vtimezone:
        out += _VTIMEZONE[tz]

    for session in sessions:
        ymd = _parse_date(session.get("date", ""), year) if year else None
        times = _parse_time(session.get("time", ""))

        out += "BEGIN:VEVENT\r\n"
        out += _fold_prop("UID", f"{uuid.uuid4()}@abstract-searcher")
        out += _fold_prop("SUMMARY", _ics_escape(_build_summary(session)))

        if ymd and times:
            y, mo, d = ymd
            (sh, sm), (eh, em) = times
            local_start = f"{y:04d}{mo:02d}{d:02d}T{sh:02d}{sm:02d}00"
            local_end   = f"{y:04d}{mo:02d}{d:02d}T{eh:02d}{em:02d}00"
            if has_vtimezone:
                out += _fold_prop("DTSTART", local_start, f"TZID={tz}")
                out += _fold_prop("DTEND",   local_end,   f"TZID={tz}")
            else:
                out += _fold_prop("DTSTART", _to_utc_str(y, mo, d, sh, sm, tz_offset_min))
                out += _fold_prop("DTEND",   _to_utc_str(y, mo, d, eh, em, tz_offset_min))

        if session.get("room"):
            out += _fold_prop("LOCATION", _ics_escape(session["room"]))

        out += _fold_prop("DESCRIPTION", _build_description(session, event_name))
        out += "END:VEVENT\r\n"

    out += "END:VCALENDAR\r\n"

    # write_bytes preserves CRLF on Windows (write_text may translate \n → \r\n)
    Path(output_path).write_bytes(out.encode("utf-8"))
