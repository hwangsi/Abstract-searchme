"""KCR (Korean Congress of Radiology) program PDF adapter.

Parses the structured KCR layout:
  SESSION_CODE  Session Title
  Sep. DD (Day), HH:MM-HH:MM
  Room
  Chairperson(s):  Name  Affiliation
  [Name  Affiliation]*          <- additional chairs
  TALK_CODE
  HH:MM or HH:MM-HH:MM
  Title
  Author1, Author2, ..., AuthorN   <- superscript refs inline (e.g. 'Name1')
  1AffiliationA, 2AffiliationB     <- numbered; may span multiple lines
  email (separate line, optional)

Returns a flat list of role records (one per person per session).
Role values: "chair" | "speaker" | "discussant"
"""

import re
from pathlib import Path
import fitz

from core.adapters.affil_refs import parse_affil_dict, resolve_affil, parse_author_with_refs

EVENT_META = {
    "event_name": "KCR 2025",
    "event_location": "Seoul, Korea",
    "event_timezone": "Asia/Seoul",
}

# ── regexes ────────────────────────────────────────────────────────────────────

_TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\b")
_DATE_RE = re.compile(r"(Sep\.\s+\d{1,2}\s+\([A-Za-z]+\)),\s+(\d{1,2}:\d{2}-\d{1,2}:\d{2})")
_SESSION_HDR_RE = re.compile(r"^(.{2,20}?)\s{2,}(.+)$")
_CHAIR_RE = re.compile(r"Chairperson\(?s?\)?:|Moderator:|Chair:|좌장:")
_DISC_RE = re.compile(r"Discussants?:|Panelists?:")
_EXTRA_CHAIR_RE = re.compile(r"^([A-Z][a-z]+(?:[-\s][A-Z]?[a-z]+)+)\s{2,}([A-Z].+)$")
_TALK_CODE_RE = re.compile(r"^[A-Z].{0,20}-[A-Z]{2}-\d+|^[A-Z]{2}\s\d{2}-\d{2}$|^\w+-\d+$")
_COUNTRY_RE = re.compile(
    r"\b(Korea|USA|Japan|France|UK|Germany|Netherlands|Saudi Arabia|Belgium|"
    r"China|Italy|Spain|Egypt|UAE|Switzerland|Australia|Vietnam|Philippines|"
    r"Czech Republic|Norway|Sweden|Denmark|Brazil|Argentina|India|Turkey)\b"
)
_AFFIL_RE = re.compile(r"\b(?:University|Hospital|Institute|Medical|Center|College|School)\b")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# ── helpers ────────────────────────────────────────────────────────────────────

def _is_list_page(lines: list[str]) -> bool:
    """True for 'List of Chairpersons' pages: many country entries, few times."""
    n_time = sum(1 for l in lines if _TIME_RE.search(l))
    n_country = sum(1 for l in lines if _COUNTRY_RE.search(l))
    return n_time < 3 and n_country >= 20


def _split_chair_line(text: str) -> tuple[str, str]:
    """'Name  Affiliation' -> (name, affiliation)."""
    text = text.replace("\x07", "").strip()
    m = re.match(r"^(.+?)\s{2,}(.+)$", text)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return text.strip(), ""


def _is_extra_chair(line: str) -> tuple[bool, str, str]:
    """Check if line is an additional Chairperson entry."""
    m = _EXTRA_CHAIR_RE.match(line)
    if m:
        return True, m.group(1).strip(), m.group(2).strip()
    return False, "", ""


def _is_talk_code(line: str) -> bool:
    return bool(_TALK_CODE_RE.match(line))


def _is_affil_continuation(line: str) -> bool:
    """True for lines like 'Medicine, Korea' that continue a wrapped affiliation."""
    if _COUNTRY_RE.search(line) and len(line) < 50:
        return True
    if _AFFIL_RE.search(line) and len(line) < 80:
        return True
    return False


def _parse_authors_with_refs(raw: str) -> tuple[list[str], list[list[int]]]:
    """Comma-separated author line -> (clean names, per-author ref lists).

    E.g. 'Joon-Il Choi1, Seo Yeon Youn2' -> (['Joon-Il Choi', 'Seo Yeon Youn'], [[1], [2]])
    """
    names: list[str] = []
    refs_list: list[list[int]] = []
    for token in raw.split(","):
        name, refs = parse_author_with_refs(token)
        if len(name.split()) >= 2:
            names.append(name)
            refs_list.append(refs)
    return names, refs_list


def _clean_affil(raw: str) -> str:
    """Strip email and trailing punctuation from affiliation string."""
    return _EMAIL_RE.sub("", raw).strip().rstrip(".,").strip()


# ── main parser ────────────────────────────────────────────────────────────────

def parse(pdf_path: str | Path) -> list[dict]:
    doc = fitz.open(str(pdf_path))
    page_lines: list[tuple[int, str]] = []  # (page_num_1based, text)

    for pn in range(doc.page_count):
        raw_lines = [l.strip() for l in doc[pn].get_text().splitlines() if l.strip()]
        if not _is_list_page(raw_lines):
            for l in raw_lines:
                page_lines.append((pn + 1, l))
    doc.close()

    records: list[dict] = []

    # Session context
    ctx: dict = {"date": "", "time": "", "room": "", "code": "", "title": "", "page": 0}
    in_chairs = False
    current_label_role = "chair"  # "chair" | "discussant"

    # Talk context
    talk_code = ""
    talk_time = ""
    talk_title_parts: list[str] = []
    in_talk_title = False
    in_talk_author = False
    # pending_talk buffers (authors, refs, title, tcode, ttime, page) between
    # the author line and the affiliation block.
    pending_talk: dict | None = None
    pending_affil_parts: list[str] = []

    def _emit_person(name, affil, role):
        records.append({
            "page": ctx["page"],
            "date": ctx["date"],
            "time": ctx["time"],
            "room": ctx["room"],
            "session_code": ctx["code"],
            "session_title": ctx["title"],
            "role": role,
            "is_primary_author": False,
            "person": name,
            "affiliation": affil,
            "talk_title": "",
        })

    def _flush_pending() -> None:
        nonlocal pending_talk, pending_affil_parts
        if pending_talk is None:
            pending_affil_parts = []
            return
        affil_raw = _clean_affil(" ".join(pending_affil_parts))
        affil_dict = parse_affil_dict(affil_raw)
        authors = pending_talk["authors"]
        refs_list = pending_talk["refs"]
        for idx, (name, refs) in enumerate(zip(authors, refs_list)):
            affil = resolve_affil(refs, affil_dict, fallback=affil_raw)
            records.append({
                "page": pending_talk["page"],
                "date": ctx["date"],
                "time": pending_talk["ttime"] or ctx["time"],
                "room": ctx["room"],
                "session_code": ctx["code"],
                "session_title": ctx["title"],
                "role": "speaker",
                "is_primary_author": (idx == 0),
                "person": name,
                "affiliation": affil,
                "talk_title": pending_talk["title"],
                "authors_all": authors,
            })
        pending_talk = None
        pending_affil_parts = []

    n = len(page_lines)
    i = 0

    while i < n:
        pn, line = page_lines[i]

        # ── date line -> new session ───────────────────────────────────────────
        dm = _DATE_RE.search(line)
        if dm:
            _flush_pending()
            in_chairs = False
            in_talk_title = False
            in_talk_author = False
            talk_code = talk_time = ""
            talk_title_parts = []

            date = dm.group(1)
            session_time = dm.group(2)
            code, title = "", ""
            for j in range(i - 1, max(i - 7, -1), -1):
                candidate = page_lines[j][1]
                m = _SESSION_HDR_RE.match(candidate)
                if m and not _DATE_RE.search(candidate) and not _TIME_RE.search(candidate.split()[0] if candidate.split() else ""):
                    code_candidate = m.group(1).rstrip()
                    if not _AFFIL_RE.search(code_candidate) and len(code_candidate) <= 20:
                        code = code_candidate
                        title = m.group(2).strip()
                        break
            room = ""
            if i + 1 < n:
                next_l = page_lines[i + 1][1]
                if not _DATE_RE.search(next_l) and not _CHAIR_RE.search(next_l) and not _is_talk_code(next_l):
                    room = next_l
            ctx = {"date": date, "time": session_time, "room": room, "code": code, "title": title, "page": pn}
            i += 1
            continue

        # ── accumulate affiliation lines after author line ─────────────────────
        if in_talk_author:
            is_structural = (
                _is_talk_code(line) or _DATE_RE.search(line)
                or _CHAIR_RE.search(line) or _DISC_RE.search(line)
            )
            is_email_only = bool(_EMAIL_RE.search(line)) and not _EMAIL_RE.sub("", line).strip()

            if is_email_only:
                _flush_pending()
                in_talk_author = False
                i += 1
                continue

            if is_structural:
                _flush_pending()
                in_talk_author = False
                # fall through to process the structural line below
            else:
                pending_affil_parts.append(line)
                i += 1
                continue

        # ── Chairperson / Moderator / 좌장 line ───────────────────────────────
        if _CHAIR_RE.search(line):
            in_talk_title = False
            in_talk_author = False
            in_chairs = True
            current_label_role = "chair"
            rest = re.sub(r"Chairperson\(?s?\)?:|Moderator:|Chair:|좌장:", "", line).strip()
            if rest:
                name, affil = _split_chair_line(rest)
                if name:
                    _emit_person(name, affil, "chair")
            i += 1
            continue

        # ── Discussant / Panelist line ─────────────────────────────────────────
        if _DISC_RE.search(line):
            in_talk_title = False
            in_talk_author = False
            in_chairs = True
            current_label_role = "discussant"
            rest = re.sub(r"Discussants?:|Panelists?:", "", line).strip()
            if rest:
                name, affil = _split_chair_line(rest)
                if name:
                    _emit_person(name, affil, "discussant")
            i += 1
            continue

        # ── additional names in the current label block ────────────────────────
        if in_chairs:
            ok, name, affil = _is_extra_chair(line)
            if ok:
                _emit_person(name, affil, current_label_role)
                i += 1
                continue
            if _is_affil_continuation(line):
                i += 1
                continue
            in_chairs = False

        # ── talk code ──────────────────────────────────────────────────────────
        if _is_talk_code(line):
            _flush_pending()
            in_talk_title = True
            in_talk_author = False
            talk_code = line
            talk_time = ""
            talk_title_parts = []
            i += 1
            if i < n:
                candidate_time = page_lines[i][1]
                if _TIME_RE.match(candidate_time) and len(candidate_time) <= 15:
                    talk_time = candidate_time
                    i += 1
            continue

        # ── talk title & speaker ───────────────────────────────────────────────
        if in_talk_title:
            # Path B: affiliation/email line detected; last title_part is the author line
            if _EMAIL_RE.search(line) or (_AFFIL_RE.search(line) and _COUNTRY_RE.search(line)):
                if talk_title_parts:
                    author_line = talk_title_parts.pop()
                    names, refs_list = _parse_authors_with_refs(author_line)
                    title_str = " ".join(talk_title_parts)
                    if names:
                        pending_talk = {
                            "authors": names,
                            "refs": refs_list,
                            "title": title_str,
                            "tcode": talk_code,
                            "ttime": talk_time,
                            "page": pn,
                        }
                        is_email_only = (bool(_EMAIL_RE.search(line)) and
                                         not _EMAIL_RE.sub("", line).strip())
                        if not is_email_only:
                            pending_affil_parts = [line]
                            in_talk_author = True
                        else:
                            _flush_pending()
                in_talk_title = False
                i += 1
                continue

            # Path A: author line heuristic
            title_so_far = " ".join(talk_title_parts)
            is_likely_author = (
                talk_title_parts and
                not line.endswith(":") and
                not re.search(r"\d", line[:20]) and
                (
                    "," in line or
                    (not re.search(r"[.!?]$", line) and
                     len(line.split()) <= 5 and
                     re.match(r"[A-Z][a-z]", line))
                )
            )
            if is_likely_author:
                names, refs_list = _parse_authors_with_refs(line)
                if not names:
                    name, refs = parse_author_with_refs(line)
                    if name.strip():
                        names = [name]
                        refs_list = [refs]
                if names:
                    pending_talk = {
                        "authors": names,
                        "refs": refs_list,
                        "title": title_so_far,
                        "tcode": talk_code,
                        "ttime": talk_time,
                        "page": pn,
                    }
                    pending_affil_parts = []
                    in_talk_title = False
                    in_talk_author = True
                i += 1
                continue

            talk_title_parts.append(line)
            i += 1
            continue

        i += 1

    _flush_pending()
    return records
