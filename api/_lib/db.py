"""Shared DB + HTTP helpers for the Vercel Python functions.

Files under api/_lib/ are not exposed as serverless functions (underscore
prefix). Each function file puts repo root + api/ on sys.path first, then
imports this module as `from _lib import db`.
"""
from __future__ import annotations

import json
import os
from typing import Any

import psycopg
from psycopg.types.json import Json


def get_conn() -> psycopg.Connection:
    """One connection per invocation — fine at colleague scale (design §8)."""
    return psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10)


# ── record row ↔ core record-dict mapping ────────────────────────────────────
# Core matcher/exporters expect the README record schema ("date", "time", …);
# the DB stores raw strings as date_raw/time_raw plus derived timestamps.

RECORD_COLS = (
    "id, person, affiliation, role, is_primary_author, date_raw, time_raw, "
    "room, session_code, session_title, talk_title, page, authors_all, starts_at"
)


def row_to_record(row: tuple) -> dict[str, Any]:
    return {
        "id": row[0],
        "person": row[1],
        "affiliation": row[2],
        "role": row[3],
        "is_primary_author": row[4],
        "date": row[5],
        "time": row[6],
        "room": row[7],
        "session_code": row[8],
        "session_title": row[9],
        "talk_title": row[10],
        "page": row[11],
        "authors_all": row[12] or [],
        # JSON-safe derived timestamp — used by the UI for time sorting (M1)
        # and by push scheduling (M2). Extra key is ignored by core exporters.
        "startsAt": row[13].isoformat() if row[13] else None,
    }


def load_records(conn: psycopg.Connection, conf_id: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {RECORD_COLS} FROM records WHERE conf_id = %s", (conf_id,))
        return [row_to_record(r) for r in cur.fetchall()]


def fetch_conference(conn: psycopg.Connection, conf_id: int) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, sha256, title, location, tz, adapter, status, error, created_at "
            "FROM conferences WHERE id = %s",
            (conf_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return {
        "id": row[0], "sha256": row[1], "title": row[2], "location": row[3],
        "tz": row[4], "adapter": row[5], "status": row[6], "error": row[7],
        "createdAt": row[8].isoformat(),
    }


def insert_records(conn: psycopg.Connection, conf_id: int, records: list[dict]) -> None:
    rows = [
        (
            conf_id,
            rec.get("person") or "",
            rec.get("affiliation") or "",
            rec.get("role") or "unknown",
            bool(rec.get("is_primary_author")),
            rec.get("date") or "",
            rec.get("time") or "",
            rec.get("_starts_at"),   # derived by parse.py, may be None
            rec.get("_ends_at"),
            rec.get("room") or "",
            rec.get("session_code") or "",
            rec.get("session_title") or "",
            rec.get("talk_title") or "",
            int(rec.get("page") or 0),
            Json(rec.get("authors_all") or []),
        )
        for rec in records
    ]
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO records (conf_id, person, affiliation, role, is_primary_author, "
            "date_raw, time_raw, starts_at, ends_at, room, session_code, session_title, "
            "talk_title, page, authors_all) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            rows,
        )


# ── BaseHTTPRequestHandler helpers ───────────────────────────────────────────

def send_json(h, status: int, obj: Any) -> None:
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    h.send_response(status)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)


def read_json_body(h) -> dict:
    """Read a JSON request body. Falls back to reading to EOF when
    Content-Length is absent (the Vercel runtime buffers bodies in BytesIO,
    so an unbounded read cannot block)."""
    length = int(h.headers.get("Content-Length") or 0)
    if length > 1_000_000:
        return {}
    try:
        raw = h.rfile.read(length) if length > 0 else h.rfile.read()
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, OSError) as e:
        h._body_err = repr(e)[:120]  # surfaced in 400 diagnostics
        return {}
