"""GET /api/search?conf=ID&q=…&mode=name|affiliation&threshold=80

Runs the core fuzzy matcher over DB-stored records — the PDF is never
re-parsed (design §1-④). This function deliberately does NOT import the
parser (pymupdf), keeping its cold start light (design §9-4).
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from http.server import BaseHTTPRequestHandler

from _lib import db
from _lib.searchlib import MAX_HITS, parse_params, run_search


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            conf_id, query, mode, threshold = parse_params(self.path)
        except ValueError as e:
            return db.send_json(self, 400, {"error": str(e)})
        try:
            with db.get_conn() as conn:
                conf, hits = run_search(conn, conf_id, query, mode, threshold)
        except ValueError as e:
            return db.send_json(self, 404, {"error": str(e)})
        db.send_json(self, 200, {
            "conference": conf,
            "total": len(hits),
            "hits": hits[:MAX_HITS],
        })
