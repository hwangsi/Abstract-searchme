"""Role-aware fuzzy name/affiliation matching with AND-token semantics.

Single-token queries  (len == 1):  original token_set_ratio behavior.
Multi-token queries   (len >= 2):  ALL tokens must independently fuzzy-match
  the target field at or above `threshold`.  This prevents "Sun" alone from
  matching "David Sun" when the full query is "Sun Young Min".
  _score is the minimum per-token score (conservative).

Dedup: results are deduplicated on the key
  (person, date, time, room, talk_title, role)
so the same person appearing N times for the same talk yields one hit.
"""

from __future__ import annotations
import re
from rapidfuzz import fuzz

_PUNCT_RE = re.compile(r'[^\w\s]')


def _strip_punct(s: str) -> str:
    """Lowercase and replace punctuation with spaces for consistent tokenisation."""
    return _PUNCT_RE.sub(' ', s.lower())


# ── primitive score ───────────────────────────────────────────────────────────

def score(query: str, target: str) -> float:
    return fuzz.token_set_ratio(query.lower(), target.lower())


# ── AND-token scoring ─────────────────────────────────────────────────────────

def _per_token_score(token: str, target: str) -> float:
    """Score one query token against a full target string.

    Pre-strips punctuation so that terminal dots and commas (e.g. "Univ."
    or "Hospital, Korea") do not confuse rapidfuzz 3.x's tokeniser.
    Without this, token_set_ratio("hospital", "...hospital, korea") returns
    ~36 instead of 100.  Stripping punctuation first restores correct behaviour
    while keeping full token-set semantics (and correctly rejecting short
    tokens like "Sun" that do not appear as real tokens in unrelated names).
    """
    return fuzz.token_set_ratio(_strip_punct(token), _strip_punct(target))


def _and_score(query: str, target: str, threshold: float) -> float | None:
    """Return minimum per-token score if ALL tokens pass threshold, else None.

    Single-token queries fall back to plain token_set_ratio (original behaviour).
    Multi-token queries use partial_ratio per token (AND semantics).
    """
    tokens = query.strip().split()
    if len(tokens) < 2:
        s = score(query, target)
        return s if s >= threshold else None

    token_scores = [_per_token_score(t, target) for t in tokens]
    if all(s >= threshold for s in token_scores):
        return min(token_scores)
    return None


# ── deduplication ─────────────────────────────────────────────────────────────

def _dedup(hits: list[dict]) -> list[dict]:
    """Keep the highest-scoring hit per (person, date, time, room, talk_title, role).

    Including `person` in the key ensures that two different people appearing
    in the same session slot are never merged.
    """
    seen: dict = {}
    for h in hits:
        key = (
            h.get('person', ''),
            h.get('date', ''),
            h.get('time', ''),
            h.get('room', ''),
            h.get('talk_title', ''),
            h.get('role', ''),
        )
        if key not in seen or h['_score'] > seen[key]['_score']:
            seen[key] = h
    return list(seen.values())


# ── public search functions ───────────────────────────────────────────────────

def matches(
    query: str,
    records: list[dict],
    threshold: float = 80.0,
    dedup: bool = True,
) -> list[dict]:
    """Return records where `person` matches `query` above threshold.

    Multi-token AND semantics: all space-separated tokens must each fuzzy-match
    the person field independently.
    """
    hits = []
    for rec in records:
        person = rec.get('person', '')
        if not person:
            continue
        s = _and_score(query, person, threshold)
        if s is not None:
            hits.append({**rec, '_score': round(s, 1)})
    hits.sort(key=lambda x: -x['_score'])
    if dedup:
        hits = _dedup(hits)
    return hits


def matches_affiliation(
    query: str,
    records: list[dict],
    threshold: float = 70.0,
    dedup: bool = True,
) -> list[dict]:
    """Return records where `affiliation` tokens match `query`.

    Uses token_set_ratio so partial institution names work:
      "Seoul National" → "Seoul National University Bundang Hospital" (score 100)
      "Bundang"        → same                                         (score 100)
    Threshold is lower than name matching (70 vs 80) to accommodate
    partial institution name queries.

    Multi-token AND semantics applied: "Seoul National Univ. Hospital" requires
    all four tokens to match, so "Chungbuk National Univ. Hospital" is rejected
    because "Seoul" does not match "Chungbuk ...".
    """
    hits = []
    for rec in records:
        affiliation = rec.get('affiliation', '')
        if not affiliation:
            continue
        s = _and_score(query, affiliation, threshold)
        if s is not None:
            hits.append({**rec, '_score': round(s, 1)})
    hits.sort(key=lambda x: -x['_score'])
    if dedup:
        hits = _dedup(hits)
    return hits
