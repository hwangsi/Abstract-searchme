"""POST /api/push — QStash webhook that delivers one scheduled Web Push.

Every request must carry a valid Upstash-Signature (JWT bound to this exact
URL and body); anything else is rejected. Deleted subscriptions and
re-scheduled reminders no-op harmlessly because the row id is the source of
truth (design §4).
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler

from _lib import db, pushlib


def _verify(signature: str, raw: bytes) -> bool:
    from qstash import Receiver

    try:
        Receiver(
            current_signing_key=os.environ["QSTASH_CURRENT_SIGNING_KEY"],
            next_signing_key=os.environ["QSTASH_NEXT_SIGNING_KEY"],
        ).verify(signature=signature, body=raw.decode("utf-8"),
                 url=f"{pushlib.base_url()}/api/push")
        return True
    except Exception:
        return False


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if 0 < length <= 10_000 else b""
        signature = self.headers.get("Upstash-Signature") or ""
        if not raw or not signature or not _verify(signature, raw):
            return db.send_json(self, 401, {"error": "invalid signature"})

        try:
            sched_id = int(json.loads(raw).get("schedId") or 0)
        except (ValueError, AttributeError):
            sched_id = 0
        if not sched_id:
            return db.send_json(self, 400, {"error": "schedId required"})

        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT sp.status, sp.fire_at, s.id, s.endpoint, s.p256dh, s.auth, s.query_name, "
                    "       r.time_raw, r.room, r.role, r.is_primary_author, r.talk_title, "
                    "       r.session_code, r.session_title, r.starts_at, r.conf_id "
                    "FROM scheduled_pushes sp "
                    "JOIN subscriptions s ON s.id = sp.sub_id "
                    "JOIN records r ON r.id = sp.record_id "
                    "WHERE sp.id = %s",
                    (sched_id,),
                )
                row = cur.fetchone()

            if row is None or row[0] != "scheduled":
                return db.send_json(self, 200, {"skipped": True})  # deleted/rescheduled

            (_, fire_at, sub_id, endpoint, p256dh, auth, query_name,
             time_raw, room, role, primary, talk_title, code, session_title,
             starts_at, conf_id) = row

            mins = int(round((starts_at - fire_at).total_seconds() / 60)) if starts_at else 0
            title = f"⏰ {mins}분 후 시작" if mins > 0 else "⏰ 곧 시작"
            summary = (f"★ {talk_title}" if primary and talk_title
                       else f"[{(role or '').capitalize()}] " + (": ".join(filter(None, [code, session_title])) or talk_title or ""))
            payload = {
                "title": title,
                "body": "\n".join(filter(None, [" · ".join(filter(None, [time_raw, room])), summary])),
                "url": f"/conf/{conf_id}?q={query_name}",
                "tag": f"sched-{sched_id}",
            }

            delivered, gone = pushlib.send_webpush(endpoint, p256dh, auth, payload)
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE scheduled_pushes SET status=%s WHERE id=%s",
                    ("sent" if delivered else "failed", sched_id),
                )
                if gone:  # phone unsubscribed — clean up remaining reminders
                    cur.execute("DELETE FROM subscriptions WHERE id=%s", (sub_id,))
            conn.commit()

        db.send_json(self, 200, {"delivered": delivered, "subscriptionGone": gone})
