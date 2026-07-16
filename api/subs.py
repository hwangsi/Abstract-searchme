"""POST /api/subs — list this device's push subscriptions (keyed by endpoint).

Authorization model: possession of the push endpoint URL is the credential —
it is an unguessable per-device URL that only the subscribing browser (and our
DB) knows. Same model as DELETE /api/subscribe.
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


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = db.read_json_body(self)
        endpoint = body.get("endpoint") or ""
        if not endpoint.startswith("https://"):
            return db.send_json(self, 400, {"error": "endpoint required"})
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT s.id, s.conf_id, c.title, s.query_name, s.offsets_min, s.created_at, "
                "  count(sp.id) FILTER (WHERE sp.status IN ('pending','scheduled') AND sp.fire_at > now()), "
                "  count(sp.id) FILTER (WHERE sp.status = 'sent') "
                "FROM subscriptions s "
                "JOIN conferences c ON c.id = s.conf_id "
                "LEFT JOIN scheduled_pushes sp ON sp.sub_id = s.id "
                "WHERE s.endpoint = %s "
                "GROUP BY s.id, c.title ORDER BY s.created_at DESC",
                (endpoint,),
            )
            subs = [
                {
                    "subId": r[0], "confId": r[1], "confTitle": r[2], "query": r[3],
                    "offsetsMin": r[4], "createdAt": r[5].isoformat(),
                    "upcoming": r[6], "sent": r[7],
                }
                for r in cur.fetchall()
            ]
        db.send_json(self, 200, {"subscriptions": subs})

    def do_DELETE(self):
        body = db.read_json_body(self)
        sub_id = int(body.get("subId") or 0)
        endpoint = body.get("endpoint") or ""
        if not (sub_id and endpoint):
            return db.send_json(self, 400, {"error": "subId and endpoint required"})
        with db.get_conn() as conn, conn.cursor() as cur:
            # endpoint must match — no deleting other devices' subscriptions
            cur.execute(
                "DELETE FROM subscriptions WHERE id=%s AND endpoint=%s", (sub_id, endpoint)
            )
            deleted = cur.rowcount
            conn.commit()
        db.send_json(self, 200, {"deleted": deleted})
