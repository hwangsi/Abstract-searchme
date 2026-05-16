"""ICR (International Congress of Radiology) 2026 program PDF adapter.

The ICR layout is a two-column visual schedule (CorelDRAW PDF):

  Page layout (approximate x ranges):
    x < 80        : left time labels (x≈57-63)
    80 ≤ x < 265  : left content column (x≈126)
    265 ≤ x < 290 : right time labels (x≈267-283)
    290 ≤ x < 330 : guest-speaker bio section (x≈296-298) — excluded
    x ≥ 330       : right content column (x≈335)

  Each page shows ONE room's full-day schedule, with morning/early afternoon
  in the left visual column and late afternoon in the right.

  A content block at y_c belongs to the time slot whose time anchor
  is the largest y_t satisfying  y_t ≤ y_c + TOLERANCE  (10 px).
  The speaker is the LAST non-trivial content line in the slot.
"""

import re
from pathlib import Path
import fitz

EVENT_META = {
    "event_name": "ICR 2026",
    "event_location": "Cartagena, Colombia",
    "event_timezone": "America/Bogota",
}

_TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\b")
_NON_SPEAKER = re.compile(
    r"(?i)\b(coffee|lunch|break|opening|ceremony|plenary|"
    r"Q&A|panel|discussion|fireside|chat|registration|"
    r"getsemani|scientific|program|guest|speaker|"
    r"ISR|Fuchs|equitable|welcome|award)\b"
)
_TOLERANCE = 10  # px


# ── column classifier ──────────────────────────────────────────────────────────

def _col(x: float) -> str:
    if x < 80:
        return "left_time"      # time labels: x≈57-63
    if x < 265:
        return "left_content"   # schedule content: x≈126
    if x < 290:
        return "right_time"     # right-side time labels: x≈267-283
    if x < 330:
        return "bio"            # guest-speaker bios: x≈296-298 — skip
    return "right_content"      # right-side schedule content: x≈335


# ── time normalisation ─────────────────────────────────────────────────────────

def _to_24h(raw: str) -> str:
    """'02:00 - 02:20 p.m.' → '14:00-14:20', '09:20 - 09:40 a.m.' → '09:20-09:40'."""
    parts = re.findall(r"(\d{1,2}):(\d{2})", raw)
    is_pm = bool(re.search(r"p\.?m\.?", raw, re.I))
    is_am = bool(re.search(r"a\.?m\.?", raw, re.I))

    def convert(h, m):
        h = int(h)
        if is_pm and h != 12:
            h += 12
        if is_am and h == 12:
            h = 0
        return f"{h:02d}:{m}"

    if len(parts) >= 2:
        return f"{convert(*parts[0])}-{convert(*parts[1])}"
    if len(parts) == 1:
        return convert(*parts[0])
    return raw.strip()


# ── main parser ────────────────────────────────────────────────────────────────

def parse(pdf_path: str | Path) -> list[dict]:
    doc = fitz.open(str(pdf_path))
    records: list[dict] = []

    for pn in range(doc.page_count):
        page = doc[pn]
        if not page.get_text().strip():
            continue

        # Collect all text spans with (y, x, text)
        spans: list[tuple[float, float, str]] = []
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            for line in b["lines"]:
                text = " ".join(s["text"] for s in line["spans"]).strip()
                if text:
                    spans.append((line["bbox"][1], line["bbox"][0], text))
        spans.sort()  # by y then x

        # ── page header (y < 130) ──────────────────────────────────────────────
        date = room = ""
        for (y, x, text) in spans:
            if y > 130:
                break
            if not date and re.search(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)", text):
                date = text.strip()
            if not room and re.search(r"\bRoom\b", text):
                room = text.strip()

        # ── classify spans into schedule columns (y > 130 only) ───────────────
        left_times:    list[tuple[float, str]] = []
        left_content:  list[tuple[float, str]] = []
        right_times:   list[tuple[float, str]] = []
        right_content: list[tuple[float, str]] = []

        for (y, x, text) in spans:
            if y <= 130:
                continue
            col = _col(x)
            has_time = bool(_TIME_RE.search(text))

            if col == "left_time":
                if has_time:
                    left_times.append((y, text))
                # else: section label ("Program", "Artificial intelligence") — ignore
            elif col == "left_content":
                left_content.append((y, text))
            elif col == "right_time":
                if has_time:
                    right_times.append((y, text))
            elif col == "right_content":
                right_content.append((y, text))
            # col == "bio": skip

        # ── assign content to time slots and extract speaker ──────────────────
        for times, contents in [(left_times, left_content), (right_times, right_content)]:
            if not times:
                continue
            times.sort()
            contents.sort()

            # Map each content line to the best (closest preceding) time slot
            slot_texts: dict[int, list[str]] = {k: [] for k in range(len(times))}
            for (yc, text) in contents:
                # Find largest time y_t ≤ yc + TOLERANCE
                best = None
                for k, (yt, _) in enumerate(times):
                    if yt <= yc + _TOLERANCE:
                        best = k
                    else:
                        break  # times are sorted; no point continuing
                if best is not None:
                    slot_texts[best].append(text)

            for k, (yt, raw_time) in enumerate(times):
                lines = slot_texts.get(k, [])
                if not lines:
                    continue

                speaker = lines[-1]
                title_parts = lines[:-1]

                # Reject if last line is clearly not a person
                if _NON_SPEAKER.search(speaker):
                    continue
                # Reject if too long to be a name (≤ 4 words)
                if len(speaker.split()) > 4:
                    continue
                # Reject single-word artifacts (page labels, etc.)
                if len(speaker.split()) < 2:
                    continue

                title = " ".join(title_parts)
                title = re.sub(r"^\.\s*", "", title).strip()

                records.append({
                    "page": pn + 1,
                    "date": date,
                    "time": _to_24h(raw_time),
                    "room": room,
                    "session_code": "",
                    "session_title": "",
                    "role": "speaker",
                    "is_primary_author": True,
                    "person": speaker,
                    "affiliation": "",
                    "talk_title": title,
                })

    doc.close()
    return records
