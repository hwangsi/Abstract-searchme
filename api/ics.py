"""GET /api/ics?conf=ID&q=…&mode=name|affiliation&threshold=80

Calendar export — reuses core.exporters.ics_exporter (VTIMEZONE, RFC 5545).
Serves as the push-independent reminder channel (design §7 이중화).
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import re
import tempfile
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from _lib import db
from _lib.searchlib import parse_params, run_search


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
        if not hits:
            return db.send_json(self, 404, {"error": "no matching sessions"})

        from core.exporters.ics_exporter import export_ics

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "schedule.ics"
            export_ics(hits, conf["tz"], out, event_name=conf["title"])
            data = out.read_bytes()

        safe = re.sub(r"[^A-Za-z0-9._ -]", "_", f"{conf['title']}_{query}_schedule.ics")
        self.send_response(200)
        self.send_header("Content-Type", "text/calendar; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{safe}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
