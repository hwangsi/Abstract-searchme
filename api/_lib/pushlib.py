"""Web Push + QStash helpers shared by subscribe.py, push.py, cron.py (design §1-⑤).

QStash free plan caps message delay at 7 days, so subscribe.py only publishes
reminders due within SCHEDULE_WINDOW; the daily cron promotes the long tail
from 'pending' to 'scheduled' as sessions come into range.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

SCHEDULE_WINDOW = timedelta(days=6)  # safety margin under QStash's 7-day max delay
DEFAULT_OFFSETS_MIN = [60, 10]


def base_url() -> str:
    """Stable public URL for QStash destinations and notification links."""
    explicit = os.environ.get("PUSH_BASE_URL")
    if explicit:
        return explicit.rstrip("/")
    host = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL", "")
    return f"https://{host}" if host else ""


def qstash_client():
    from qstash import QStash

    token = os.environ.get("QSTASH_TOKEN")
    return QStash(token) if token else None


def publish_due_pending(conn, now: datetime | None = None) -> dict:
    """Publish QStash messages for 'pending' reminders due within the window.
    Past-due pending rows are cancelled. Returns counts. No-op without a token
    (rows stay pending until the QStash integration provides QSTASH_TOKEN)."""
    now = now or datetime.now(timezone.utc)
    client = qstash_client()
    dest = f"{base_url()}/api/push"

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE scheduled_pushes SET status='cancelled' "
            "WHERE status='pending' AND fire_at <= %s",
            (now,),
        )
        cancelled = cur.rowcount
        cur.execute(
            "SELECT id, fire_at FROM scheduled_pushes "
            "WHERE status='pending' AND fire_at > %s AND fire_at <= %s "
            "ORDER BY fire_at LIMIT 400",  # QStash free tier: 500 msg/day (design §8)
            (now, now + SCHEDULE_WINDOW),
        )
        due = cur.fetchall()

    published = 0
    if client and dest.startswith("https://"):
        for sched_id, fire_at in due:
            delay = max(1, int((fire_at - now).total_seconds()))
            res = client.message.publish_json(
                url=dest,
                body={"schedId": sched_id},
                delay=delay,
                retries=2,
            )
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE scheduled_pushes SET status='scheduled', qstash_id=%s WHERE id=%s",
                    (getattr(res, "message_id", None), sched_id),
                )
            published += 1
    conn.commit()
    return {"published": published, "stillPending": len(due) - published, "cancelledPast": cancelled}


def send_webpush(endpoint: str, p256dh: str, auth: str, payload: dict) -> tuple[bool, bool]:
    """Send one notification. Returns (delivered, subscription_gone)."""
    from pywebpush import WebPushException, webpush

    try:
        webpush(
            subscription_info={"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}},
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=os.environ["VAPID_PRIVATE_KEY"],
            vapid_claims={"sub": os.environ.get("VAPID_SUBJECT", "mailto:admin@example.com")},
            ttl=3600,
        )
        return True, False
    except WebPushException as e:
        status = getattr(e.response, "status_code", None)
        return False, status in (404, 410)  # subscription expired/unsubscribed
