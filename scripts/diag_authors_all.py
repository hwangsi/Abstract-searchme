"""Diagnostic: authors_all consistency across adapters.

Uses cached JSON if PDF not available.

Usage:
    python scripts/diag_authors_all.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SOURCES = {
    "KCR": {
        "pdf": Path("data/pdfs/KCR2025_Program_Book.pdf"),
        "json": Path("data/sessions/KCR2025_Program_Book.json"),
        "adapter": "kcr",
    },
    "ICR": {
        "pdf": Path("data/pdfs/EN-ICR 2026 f. prog_110526.pdf"),
        "json": Path("data/sessions/EN-ICR 2026 f. prog_110526.json"),
        "adapter": "icr",
    },
    "GBCC": {
        "pdf": Path("data/pdfs/GBCC 2026_AbstractBook.pdf"),
        "json": None,
        "adapter": "gbcc",
    },
}


def _load(name: str, src: dict) -> list[dict] | None:
    if src["pdf"].exists():
        import importlib
        mod = importlib.import_module(f"core.adapters.{src['adapter']}")
        print(f"  Parsing {name} from PDF...")
        return mod.parse(src["pdf"])
    if src["json"] and src["json"].exists():
        print(f"  Loading {name} from JSON cache...")
        with open(src["json"], encoding="utf-8") as f:
            data = json.load(f)
        return data.get("sessions", data) if isinstance(data, dict) else data
    print(f"  {name}: no PDF or JSON found - skipping")
    return None


def _analyse(name: str, records: list[dict]) -> None:
    print(f"\n{'=' * 60}")
    print(f"Adapter: {name}  ({len(records)} total records)")
    print("=" * 60)

    # (a) role distribution
    role_counts = Counter(r.get("role", "?") for r in records)
    print("\n(a) Role distribution")
    for role, cnt in sorted(role_counts.items()):
        print(f"  {role:<15} {cnt:>5}")

    # (b/c) talk-unit grouping for speaker records
    # Key = (date, time, room, talk_title) — distinguishes individual talks
    speaker_recs = [r for r in records if r.get("role") == "speaker" and r.get("talk_title", "").strip()]

    talk_groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in speaker_recs:
        key = (r.get("date", ""), r.get("time", ""), r.get("room", ""), r.get("talk_title", ""))
        talk_groups[key].append(r)

    total_talks = len(talk_groups)
    if total_talks == 0:
        print("\n(b/c) No speaker talk groups found")
    else:
        groups_with_authors_all = sum(
            1 for g in talk_groups.values() if any(r.get("authors_all") for r in g)
        )
        groups_consistent = sum(
            1 for g in talk_groups.values()
            if all(r.get("authors_all") == g[0].get("authors_all") for r in g)
            and g[0].get("authors_all") is not None
        )
        groups_size_eq_len = sum(
            1 for g in talk_groups.values()
            if g[0].get("authors_all") and len(g[0]["authors_all"]) == len(g)
        )
        single_record_talks = sum(1 for g in talk_groups.values() if len(g) == 1)

        print(f"\n(b) Talk groups (speaker, non-empty talk_title): {total_talks}")
        print(f"  authors_all filled   : {groups_with_authors_all}/{total_talks} ({100*groups_with_authors_all/total_talks:.0f}%)")
        print(f"  authors_all consistent in group: {groups_consistent}/{total_talks} ({100*groups_consistent/total_talks:.0f}%)")
        print(f"  authors_all len == group size  : {groups_size_eq_len}/{total_talks} ({100*groups_size_eq_len/total_talks:.0f}%)")
        print(f"  single-record talks (likely 1st-author-only): {single_record_talks}/{total_talks} ({100*single_record_talks/total_talks:.0f}%)")

    # (c) speaker total person count
    print(f"\n(c) Speaker records: {len(speaker_recs)}")
    multi_record_talks = [(k, g) for k, g in talk_groups.items() if len(g) > 1]
    print(f"  Multi-author talks (>1 record per talk): {len(multi_record_talks)}")
    if multi_record_talks:
        print("  Sample (first 3):")
        for key, group in multi_record_talks[:3]:
            print(f"    talk={key[3][:50]!r}")
            for r in group:
                print(f"      person={r['person']!r}, authors_all_len={len(r.get('authors_all') or [])}")

    # (d) chair/discussant authors_all check
    non_speaker = [r for r in records if r.get("role") in ("chair", "discussant", "panelist")]
    if non_speaker:
        filled = sum(1 for r in non_speaker if r.get("authors_all"))
        print(f"\n(d) Chair/discussant/panelist: {len(non_speaker)} records, "
              f"authors_all filled: {filled} ({100*filled/len(non_speaker):.0f}%)")

    # (e) author lines with potential "Surname, Firstname" pattern
    print(f"\n(e) Potential 'Surname, First' comma-in-name check (speaker person samples):")
    comma_names = [r["person"] for r in speaker_recs if "," in r.get("person", "")]
    if comma_names:
        print(f"  WARNING: {len(comma_names)} speaker records with comma in person field:")
        for n in comma_names[:5]:
            print(f"    {n!r}")
    else:
        print("  None found - simple comma split is safe for person names")


def main():
    for name, src in SOURCES.items():
        records = _load(name, src)
        if records is not None:
            _analyse(name, records)

    print("\n\nDIAGNOSIS SUMMARY")
    print("=" * 60)
    print("Expected (after fix):")
    print("  KCR: authors_all filled for all speaker records")
    print("       group size == authors_all len (all co-authors emitted)")
    print("  ICR: each talk has 1 record (visual layout, no co-authors)")
    print("       authors_all=[person] after normalize_records")
    print("  GBCC: already correct (index pages emit all co-authors)")


if __name__ == "__main__":
    main()
