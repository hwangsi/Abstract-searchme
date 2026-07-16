"""Search logic shared by api/search.py and api/ics.py.

Lives in _lib because Vercel bundles each function separately — one function
file must never import another function file (only _lib/ and core/ are
included in every bundle via vercel.json includeFiles).
"""
from __future__ import annotations

import urllib.parse

from _lib import db

MAX_HITS = 500


def run_search(conn, conf_id: int, query: str, mode: str, threshold: float):
    """Returns (conference, hits). Raises ValueError with a user-facing message."""
    from core.search.matcher import matches, matches_affiliation

    conf = db.fetch_conference(conn, conf_id)
    if conf is None:
        raise ValueError("conference not found")
    if conf["status"] != "ready":
        raise ValueError(f"conference status is {conf['status']}")
    records = db.load_records(conn, conf_id)
    if mode == "affiliation":
        hits = matches_affiliation(query, records, threshold=threshold)
    else:
        hits = matches(query, records, threshold=threshold)
    return conf, hits


def parse_params(path: str) -> tuple[int, str, str, float]:
    """Parse ?conf=&q=&mode=&threshold= — shared param contract for search/ics."""
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
    get = lambda k, d="": (qs.get(k) or [d])[0]
    conf_id = int(get("conf", "0") or 0)
    query = get("q").strip()
    mode = get("mode", "name")
    if mode not in ("name", "affiliation"):
        mode = "name"
    threshold = max(0.0, min(100.0, float(get("threshold", "80") or 80)))
    if conf_id <= 0 or not query:
        raise ValueError("conf and q are required")
    return conf_id, query, mode, threshold
