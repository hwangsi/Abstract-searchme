"""Ground truth regression tests.

All PDF files are read from data/pdfs/. Run with:
    python -m pytest tests/ -v
"""

from __future__ import annotations

from collections import Counter, defaultdict

import pytest
from pathlib import Path

from core.search.matcher import matches, matches_affiliation
from core.adapters import kcr, icr, gbcc

DATA = Path("data/pdfs")

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _pages(hits: list[dict]) -> list[int]:
    return sorted(h["page"] for h in hits)

def _talks(hits: list[dict]) -> list[str]:
    return sorted(h.get("talk_title", "") for h in hits)


# ---------------------------------------------------------------------------
# fixtures: raw adapter output (existing tests — unchanged)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def icr_records():
    return icr.parse(DATA / "EN-ICR 2026 f. prog_110526.pdf")

@pytest.fixture(scope="session")
def kcr_records():
    return kcr.parse(DATA / "KCR2025_Program_Book.pdf")

@pytest.fixture(scope="session")
def gbcc_records():
    return gbcc.parse(DATA / "GBCC 2026_AbstractBook.pdf")


# ---------------------------------------------------------------------------
# fixtures: normalized output (invariant + new tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def kcr_normalized():
    from core.adapters import load_pdf
    records, _ = load_pdf(DATA / "KCR2025_Program_Book.pdf")
    return records

@pytest.fixture(scope="session")
def icr_normalized():
    from core.adapters import load_pdf
    records, _ = load_pdf(DATA / "EN-ICR 2026 f. prog_110526.pdf")
    return records

@pytest.fixture(scope="session")
def gbcc_normalized():
    from core.adapters import load_pdf
    records, _ = load_pdf(DATA / "GBCC 2026_AbstractBook.pdf")
    return records


# ---------------------------------------------------------------------------
# existing ground truth (must not regress)
# ---------------------------------------------------------------------------

def test_icr_sung_hwang_2_hits(icr_records):
    hits = matches("Sung Hwang", icr_records)
    assert len(hits) == 2, f"Expected 2 hits, got {len(hits)}: {_talks(hits)}"
    assert all(h["role"] == "speaker" for h in hits)
    assert all(h["is_primary_author"] for h in hits)


def test_kcr_jin_mo_goo_3_hits(kcr_records):
    hits = matches("Jin Mo Goo", kcr_records)
    assert len(hits) == 3, f"Expected 3 hits, got {len(hits)}: {_talks(hits)}"
    assert all(h["role"] == "chair" for h in hits)


# ---------------------------------------------------------------------------
# GBCC ground truth
# ---------------------------------------------------------------------------

def test_gbcc_sun_young_min_3_hits(gbcc_records):
    hits = matches("Sun Young Min", gbcc_records)
    pages = _pages(hits)
    assert len(hits) == 3, f"Expected 3 hits, got {len(hits)}: pages={pages}"
    assert 269 in pages, f"Missing page 269 (PO006): pages={pages}"
    assert 363 in pages, f"Missing page 363 (PO090): pages={pages}"
    assert 504 in pages, f"Missing page 504 (PO287): pages={pages}"


def test_gbcc_woo_kyung_moon_1_hit(gbcc_records):
    hits = matches("Woo Kyung Moon", gbcc_records)
    assert len(hits) == 1, f"Expected 1 hit, got {len(hits)}: {_talks(hits)}"
    h = hits[0]
    assert h["page"] == 23, f"Expected page 23, got {h['page']}"
    assert "Seoul National" in h.get("affiliation", ""), (
        f"Missing 'Seoul National' in affiliation: {h.get('affiliation')}"
    )


def test_gbcc_affiliation_seoul_national_univ_hospital(gbcc_records):
    hits = matches_affiliation("Seoul National Univ. Hospital", gbcc_records)
    pages = _pages(hits)
    assert 23 in pages, (
        f"Page 23 (Woo Kyung Moon) missing from affiliation results: pages={pages}"
    )
    affiliations = [h.get("affiliation", "") for h in hits]
    chungbuk_hits = [a for a in affiliations if "Chungbuk" in a]
    assert not chungbuk_hits, (
        f"Chungbuk should not match 'Seoul National Univ. Hospital': {chungbuk_hits}"
    )


# ---------------------------------------------------------------------------
# KCR affiliation / co-author regressions (Stage 5e-fix + 5e-fix-2)
# ---------------------------------------------------------------------------

def test_kcr_speaker_affiliation_filled(kcr_records):
    """Speaker records must have non-empty affiliation after Stage 5e-fix."""
    speakers = [r for r in kcr_records if r.get("role") == "speaker"]
    filled = [r for r in speakers if r.get("affiliation", "").strip()]
    fill_rate = len(filled) / len(speakers) if speakers else 0
    assert fill_rate > 0.5, (
        f"Speaker affiliation fill rate too low: {len(filled)}/{len(speakers)} ({fill_rate:.0%})"
    )


def test_kcr_affiliation_seoul_national_includes_speakers(kcr_records):
    """'Seoul National University' affiliation search must return speaker records."""
    hits = matches_affiliation("Seoul National University", kcr_records)
    role_dist = Counter(h["role"] for h in hits)
    assert role_dist.get("speaker", 0) > 0, (
        f"Expected at least one speaker in affiliation results, got: {dict(role_dist)}"
    )
    assert role_dist.get("chair", 0) >= 25, (
        f"Chair count unexpectedly low after fix: {dict(role_dist)}"
    )


def test_kcr_coauthor_records_present(kcr_records):
    """After Stage 5e-fix-2: KCR must have multi-author talks (authors_all len >= 2)."""
    multi_author = [
        r for r in kcr_records
        if r.get("role") == "speaker" and len(r.get("authors_all") or []) >= 2
    ]
    assert len(multi_author) > 0, (
        "No multi-author speaker records found; co-author emit may be broken"
    )


def test_kcr_affiliation_snuh_speaker_lower_bound(kcr_records):
    """'Seoul National University Hospital' speaker count must be significant after fix."""
    hits = matches_affiliation("Seoul National University Hospital", kcr_records)
    role_dist = Counter(h["role"] for h in hits)
    assert role_dist.get("speaker", 0) >= 10, (
        f"Expected >= 10 speakers, got: {dict(role_dist)}"
    )


# ---------------------------------------------------------------------------
# Invariants I1-I5 (normalized records, all adapters)
# ---------------------------------------------------------------------------

def _check_invariants(records: list[dict], adapter_name: str) -> None:
    """Assert I1-I5 on a normalized record list."""
    # Group speaker records by talk key
    talk_groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in records:
        if r.get("role") == "speaker" and r.get("talk_title", "").strip():
            key = (r.get("date", ""), r.get("time", ""), r.get("room", ""), r.get("talk_title", ""))
            talk_groups[key].append(r)

    for key, group in talk_groups.items():
        talk_label = f"{adapter_name} talk={key[3][:40]!r}"

        # I2: all records in group share the same authors_all
        authors_all_values = [tuple(r.get("authors_all") or []) for r in group]
        assert len(set(authors_all_values)) == 1, (
            f"I2 violated: authors_all not consistent in {talk_label}: {authors_all_values}"
        )

        # I3: authors_all is non-empty
        authors_all = group[0].get("authors_all") or []
        assert len(authors_all) > 0, f"I3 violated: empty authors_all in {talk_label}"

        # I4: exactly one primary_author per group (the first in authors_all)
        primary_persons = [r["person"] for r in group if r.get("is_primary_author")]
        assert len(primary_persons) == 1, (
            f"I4 violated: expected 1 primary, got {primary_persons} in {talk_label}"
        )
        assert primary_persons[0] == authors_all[0], (
            f"I4 violated: primary {primary_persons[0]!r} != authors_all[0] {authors_all[0]!r}"
            f" in {talk_label}"
        )

    # I5: chair/discussant/panelist have authors_all = [person]
    for r in records:
        if r.get("role") in ("chair", "discussant", "panelist"):
            aa = r.get("authors_all") or []
            assert len(aa) == 1, (
                f"I5 violated: {r['role']} {r['person']!r} has authors_all={aa}"
            )
            assert aa[0] == r.get("person"), (
                f"I5 violated: {r['role']} authors_all[0]={aa[0]!r} != person={r.get('person')!r}"
            )


def test_invariants_kcr(kcr_normalized):
    _check_invariants(kcr_normalized, "KCR")


def test_invariants_icr(icr_normalized):
    _check_invariants(icr_normalized, "ICR")


def test_invariants_gbcc(gbcc_normalized):
    _check_invariants(gbcc_normalized, "GBCC")


# ---------------------------------------------------------------------------
# regression: single-token path still works after AND-token change
# ---------------------------------------------------------------------------

def test_single_token_still_works(kcr_records):
    hits = matches("Goo", kcr_records)
    persons = [h["person"] for h in hits]
    assert any("Goo" in p for p in persons), (
        f"Single-token 'Goo' found no Goo-containing names: {persons[:5]}"
    )


# ---------------------------------------------------------------------------
# Stage 5e-fix-3: superscript-based per-author affiliation mapping
# ---------------------------------------------------------------------------

def test_kcr_no_trailing_digit_in_person(kcr_normalized):
    """After normalize_records, no person field should end with a digit."""
    import re
    bad = [r["person"] for r in kcr_normalized if re.search(r"\d$", r.get("person", ""))]
    assert not bad, f"Persons with trailing digit found: {bad[:5]}"


def test_kcr_p55_magnus_hcc_superscript_snuh_authors(kcr_normalized):
    """MAGNUS-HCC talk (p55): authors with ref=2 must map to Seoul National University Hospital.

    Joon-Il Choi1, Seo Yeon Youn2, Moon Hyung Choi3, Chang Hee Lee4,
    Jeong Hee Yoon2, Tae Wook Kang5
    -> refs [2] -> Seoul National University Hospital, Korea
    """
    from core.search.matcher import matches_affiliation

    hits = matches_affiliation("Seoul National University Hospital", kcr_normalized)
    snuh_persons = {h["person"] for h in hits if h.get("role") == "speaker"}

    assert "Seo Yeon Youn" in snuh_persons, (
        f"Seo Yeon Youn (ref=2, SNUH) missing from SNUH affil results: {snuh_persons}"
    )
    assert "Jeong Hee Yoon" in snuh_persons, (
        f"Jeong Hee Yoon (ref=2, SNUH) missing from SNUH affil results: {snuh_persons}"
    )


def test_kcr_affiliation_snuh_total_count_not_regressed(kcr_normalized):
    """Total SNUH affiliation hits must not regress below 49 after fix-3."""
    from core.search.matcher import matches_affiliation

    hits = matches_affiliation("Seoul National University Hospital", kcr_normalized)
    assert len(hits) >= 49, (
        f"SNUH affiliation total count regressed: got {len(hits)}, expected >= 49"
    )


# ---------------------------------------------------------------------------
# Stage 5e-fix-4: new talk code formats + author heuristic guards
# ---------------------------------------------------------------------------

def test_kcr_affiliation_bundang_lower_bound(kcr_normalized):
    """'Seoul National University Bundang' must return >= 20 deduped hits after fix-4.

    Ground truth: ~25 PDF pages contain Bundang Hospital entries.
    Before fix-4 the app returned only 10 (new talk code formats were not
    recognized, so speaker records were never created for those sessions).
    """
    from core.search.matcher import matches_affiliation

    hits = matches_affiliation("Seoul National University Bundang", kcr_normalized)
    assert len(hits) >= 20, (
        f"Bundang affiliation hit count regressed: got {len(hits)}, expected >= 20"
    )
