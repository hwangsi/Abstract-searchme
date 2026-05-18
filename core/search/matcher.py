"""Role-aware fuzzy name matching.

The query is matched against the `person` field only.
- For Chairperson/Moderator: match any chairperson name
- For Speaker: match ONLY if person is first author (already filtered by adapter)

Uses rapidfuzz token_set_ratio so word-order variants match:
  "Sung Hwang" matches "Hwang, Sung", "Sung Il Hwang", etc.
"""

from __future__ import annotations
from rapidfuzz import fuzz


def score(query: str, name: str) -> float:
    return fuzz.token_set_ratio(query.lower(), name.lower())


def matches(
    query: str,
    records: list[dict],
    threshold: float = 80.0,
) -> list[dict]:
    """Return records where `person` matches `query` above threshold."""
    hits = []
    for rec in records:
        person = rec.get("person", "")
        if not person:
            continue
        s = score(query, person)
        if s >= threshold:
            hits.append({**rec, "_score": round(s, 1)})
    hits.sort(key=lambda x: -x["_score"])
    return hits


def matches_affiliation(
    query: str,
    records: list[dict],
    threshold: float = 70.0,
) -> list[dict]:
    """Return records where `affiliation` tokens match `query`.

    Uses token_set_ratio so partial institution names work:
      "Seoul National" → "Seoul National University Bundang Hospital" (score 100)
      "Bundang"        → same                                         (score 100)
    Threshold is lower than name matching (70 vs 80) to accommodate
    partial institution name queries.
    """
    hits = []
    for rec in records:
        affiliation = rec.get("affiliation", "")
        if not affiliation:
            continue
        s = score(query, affiliation)
        if s >= threshold:
            hits.append({**rec, "_score": round(s, 1)})
    hits.sort(key=lambda x: -x["_score"])
    return hits
