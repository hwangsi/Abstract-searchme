"""Post-processing applied to every adapter's output.

Enforces the invariants that all adapters must satisfy:
  I1. Every author of a talk gets their own record.
  I2. All records for the same talk share an identical authors_all list.
  I3. authors_all order == original appearance order; index 0 = first author.
  I4. is_primary_author is True iff person == authors_all[0].
  I5. chair/discussant/panelist records have authors_all = [person].
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict

_TRAILING_DIGIT_RE = re.compile(r"\d+$")


def _strip_trailing_digits(name: str) -> str:
    return _TRAILING_DIGIT_RE.sub("", name).strip()


def normalize_records(records: list[dict]) -> list[dict]:
    """Apply I1–I5 and dedup. Safe to call on any adapter's raw output."""
    # ── strip trailing superscript digits left in person / authors_all ────────
    for r in records:
        person = r.get("person", "")
        cleaned = _strip_trailing_digits(person)
        if cleaned != person:
            print(
                f"[post] stripped trailing digit: {person!r} -> {cleaned!r}",
                file=sys.stderr,
            )
            r["person"] = cleaned
        if r.get("authors_all"):
            r["authors_all"] = [_strip_trailing_digits(a) for a in r["authors_all"]]

    # ── dedup on full identity key ─────────────────────────────────────────────
    seen: set[tuple] = set()
    deduped: list[dict] = []
    for r in records:
        key = (
            r.get("date", ""), r.get("time", ""), r.get("room", ""),
            r.get("talk_title", ""), r.get("role", ""), r.get("person", ""),
        )
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    records = deduped

    # ── I5: chair / discussant / panelist → authors_all = [person] ────────────
    for r in records:
        if r.get("role") in ("chair", "discussant", "panelist"):
            r["authors_all"] = [r.get("person", "")]
            r["is_primary_author"] = True

    # ── I2–I4: speaker records grouped by talk ─────────────────────────────────
    # Group key: (date, time, room, talk_title) — identifies one talk.
    # Records without talk_title are treated as solo entries.
    talk_groups: dict[tuple, list[dict]] = defaultdict(list)
    solo_speakers: list[dict] = []

    for r in records:
        if r.get("role") == "speaker":
            tt = r.get("talk_title", "").strip()
            if tt:
                key = (r.get("date", ""), r.get("time", ""), r.get("room", ""), tt)
                talk_groups[key].append(r)
            else:
                solo_speakers.append(r)

    for group in talk_groups.values():
        # Prefer an existing authors_all (adapter may have set it correctly)
        existing = next(
            (r["authors_all"] for r in group if r.get("authors_all")),
            None,
        )
        if existing:
            authors_all = existing
        else:
            # Reconstruct from group persons in record order
            authors_all = [r.get("person", "") for r in group]

        primary = authors_all[0] if authors_all else ""
        for r in group:
            r["authors_all"] = authors_all
            r["is_primary_author"] = (r.get("person", "") == primary)

    for r in solo_speakers:
        if not r.get("authors_all"):
            r["authors_all"] = [r.get("person", "")]
        r["is_primary_author"] = True

    return records
