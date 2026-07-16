"""GET /api/cron — daily Vercel Cron: promote 'pending' reminders into QStash
once they fall inside the 7-day delay window (see _lib/pushlib.py).

Vercel authenticates cron invocations with `Authorization: Bearer $CRON_SECRET`.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import hmac
from http.server import BaseHTTPRequestHandler

from _lib import db, pushlib


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        secret = os.environ.get("CRON_SECRET", "")
        auth = self.headers.get("Authorization") or ""
        if not secret or not hmac.compare_digest(auth, f"Bearer {secret}"):
            return db.send_json(self, 401, {"error": "unauthorized"})
        with db.get_conn() as conn:
            counts = pushlib.publish_due_pending(conn)
        db.send_json(self, 200, counts)
