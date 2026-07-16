"""GET /api/conferences — shared-cache conference list for the home page."""
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


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT c.id, c.title, c.location, c.tz, c.adapter, c.status, c.created_at, "
                "       (SELECT count(*) FROM records r WHERE r.conf_id = c.id) "
                "FROM conferences c ORDER BY c.created_at DESC LIMIT 100"
            )
            rows = cur.fetchall()
        db.send_json(self, 200, {
            "conferences": [
                {
                    "id": r[0], "title": r[1], "location": r[2], "tz": r[3],
                    "adapter": r[4], "status": r[5], "createdAt": r[6].isoformat(),
                    "recordCount": r[7],
                }
                for r in rows
            ]
        })
