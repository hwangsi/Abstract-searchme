"""Ground truth regression tests.

All PDF files are read from data/pdfs/. Run with:
    python -m pytest tests/ -v
"""

from __future__ import annotations

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
# fixture: parsed records (cached per adapter per test session)
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
# GBCC ground truth (new)
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
    # Woo Kyung Moon (page 23) must appear
    assert 23 in pages, (
        f"Page 23 (Woo Kyung Moon) missing from affiliation results: pages={pages}"
    )
    # Chungbuk National Univ. Hospital must NOT appear
    affiliations = [h.get("affiliation", "") for h in hits]
    chungbuk_hits = [a for a in affiliations if "Chungbuk" in a]
    assert not chungbuk_hits, (
        f"Chungbuk should not match 'Seoul National Univ. Hospital': {chungbuk_hits}"
    )


# ---------------------------------------------------------------------------
# regression: single-token path still works after AND-token change
# ---------------------------------------------------------------------------

def test_single_token_still_works(kcr_records):
    # "Goo" alone should still find Jin Mo Goo (single-token fallback)
    hits = matches("Goo", kcr_records)
    persons = [h["person"] for h in hits]
    assert any("Goo" in p for p in persons), (
        f"Single-token 'Goo' found no Goo-containing names: {persons[:5]}"
    )
