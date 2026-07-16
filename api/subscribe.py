"""POST   /api/subscribe — register a Web Push subscription and schedule reminders.
DELETE /api/subscribe — remove a subscription (cascades its scheduled pushes).

The server re-runs the search (client hit lists are not trusted) and schedules
per future session × offset. Reminders beyond QStash's delay window stay
'pending' and are promoted by the daily cron (see _lib/pushlib.py).
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler

from _lib import db, pushlib
from _lib.searchlib import run_search


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = db.read_json_body(self)
        conf_id = int(body.get("confId") or 0)
        query = (body.get("q") or "").strip()
        mode = body.get("mode") if body.get("mode") in ("name", "affiliation") else "name"
        threshold = max(0.0, min(100.0, float(body.get("threshold") or 80)))
        offsets = body.get("offsetsMin") or pushlib.DEFAULT_OFFSETS_MIN
        offsets = sorted({int(o) for o in offsets if 0 < int(o) <= 24 * 60}, reverse=True)
        sub = body.get("subscription") or {}
        endpoint = sub.get("endpoint") or ""
        keys = sub.get("keys") or {}

        if not (conf_id and query and offsets and endpoint.startswith("https://")
                and keys.get("p256dh") and keys.get("auth")):
            return db.send_json(self, 400, {
                "error": "invalid subscription request",
                "fields": {  # booleans only — helps callers fix their payload
                    "bodyParsed": bool(body),
                    "bodyErr": getattr(self, "_body_err", ""),
                    "confId": bool(conf_id),
                    "q": bool(query),
                    "offsetsMin": bool(offsets),
                    "endpointHttps": endpoint.startswith("https://"),
                    "p256dh": bool(keys.get("p256dh")),
                    "auth": bool(keys.get("auth")),
                },
            })

        now = datetime.now(timezone.utc)
        with db.get_conn() as conn:
            try:
                _, hits = run_search(conn, conf_id, query, mode, threshold)
            except ValueError as e:
                return db.send_json(self, 404, {"error": str(e)})

            future = [h for h in hits if h.get("startsAt")
                      and datetime.fromisoformat(h["startsAt"]) > now]

            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO subscriptions (conf_id, query_name, endpoint, p256dh, auth, offsets_min) "
                    "VALUES (%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (endpoint, conf_id, query_name) DO UPDATE "
                    "SET p256dh=EXCLUDED.p256dh, auth=EXCLUDED.auth, offsets_min=EXCLUDED.offsets_min "
                    "RETURNING id",
                    (conf_id, query, endpoint, keys["p256dh"], keys["auth"], offsets),
                )
                sub_id = cur.fetchone()[0]
                # re-subscribe = clean reschedule; orphaned QStash deliveries
                # no-op because push.py looks rows up by id (design §4).
                cur.execute("DELETE FROM scheduled_pushes WHERE sub_id=%s", (sub_id,))

                rows = []
                for h in future:
                    starts = datetime.fromisoformat(h["startsAt"])
                    for off in offsets:
                        fire_at = starts - timedelta(minutes=off)
                        if fire_at > now:
                            rows.append((sub_id, h["id"], fire_at))
                cur.executemany(
                    "INSERT INTO scheduled_pushes (sub_id, record_id, fire_at, status) "
                    "VALUES (%s,%s,%s,'pending')",
                    rows,
                )
            conn.commit()
            counts = pushlib.publish_due_pending(conn, now)

        db.send_json(self, 200, {
            "subId": sub_id,
            "sessions": len(future),
            "sessionsWithoutTime": len(hits) - len(future),
            "reminders": len(rows),
            **counts,
            "qstashConfigured": pushlib.qstash_client() is not None,
        })

    def do_DELETE(self):
        body = db.read_json_body(self)
        conf_id = int(body.get("confId") or 0)
        query = (body.get("q") or "").strip()
        endpoint = body.get("endpoint") or ""
        if not (conf_id and query and endpoint):
            return db.send_json(self, 400, {"error": "confId, q, endpoint required"})
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM subscriptions WHERE conf_id=%s AND query_name=%s AND endpoint=%s",
                (conf_id, query, endpoint),
            )
            deleted = cur.rowcount
            conn.commit()
        db.send_json(self, 200, {"deleted": deleted})
