"""POST /api/parse — download an uploaded PDF from Blob and parse it into the DB.
GET  /api/parse?sha256=… — shared-cache lookup before uploading (design §4, §6).

Idempotent on sha256: the first request claims the hash ('parsing' row); later
requests return the existing conference. A 'failed' conference may be re-parsed.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import hashlib
import re
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from _lib import db

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_PDF_BYTES = 200 * 1024 * 1024  # design §6 upload cap


def _blob_url_ok(url: str) -> bool:
    """Only fetch from Vercel Blob — never an arbitrary URL (SSRF guard)."""
    try:
        u = urllib.parse.urlparse(url)
    except ValueError:
        return False
    return u.scheme == "https" and u.hostname is not None and (
        u.hostname.endswith(".blob.vercel-storage.com")
    )


def _download(url: str, dest_dir: str, filename: str) -> Path:
    """Stream the blob to disk; returns local path. Filename is kept (sanitized)
    because adapter detection reads the PDF filename stem (core.main)."""
    safe = re.sub(r"[^A-Za-z0-9._ -]", "_", filename or "").strip() or "upload.pdf"
    if not safe.lower().endswith(".pdf"):
        safe += ".pdf"
    dest = Path(dest_dir) / safe[-100:]
    total = 0
    with urllib.request.urlopen(url, timeout=120) as resp, open(dest, "wb") as f:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_PDF_BYTES:
                raise ValueError("PDF exceeds 200MB limit")
            f.write(chunk)
    return dest


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _derive_times(records: list[dict], event_name: str, tz_name: str) -> None:
    """Fill rec['_starts_at'] / rec['_ends_at'] (aware datetimes) where the raw
    date/time strings parse; leave None otherwise (design §5). Reuses the
    battle-tested parsers from the ics exporter."""
    from zoneinfo import ZoneInfo

    from core.exporters.ics_exporter import _extract_year, _parse_date, _parse_time

    year = _extract_year(event_name or "")
    try:
        tz = ZoneInfo(tz_name or "UTC")
    except Exception:
        tz = None
    for rec in records:
        rec["_starts_at"] = rec["_ends_at"] = None
        if not (year and tz):
            continue
        ymd = _parse_date(rec.get("date") or "", year)
        times = _parse_time(rec.get("time") or "")
        if not (ymd and times):
            continue
        y, mo, d = ymd
        (sh, sm), (eh, em) = times
        try:
            start = datetime(y, mo, d, sh, sm, tzinfo=tz)
            end = datetime(y, mo, d, eh, em, tzinfo=tz)
        except ValueError:
            continue
        if end < start:  # session crossing midnight — rare, keep sane ordering
            end += timedelta(days=1)
        rec["_starts_at"], rec["_ends_at"] = start, end


def _conf_by_sha(conn, sha256: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM conferences WHERE sha256 = %s", (sha256,))
        row = cur.fetchone()
    return db.fetch_conference(conn, row[0]) if row else None


class handler(BaseHTTPRequestHandler):
    def do_GET(self):  # cache lookup
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        sha256 = (qs.get("sha256") or [""])[0].lower()
        if not _SHA256_RE.match(sha256):
            return db.send_json(self, 400, {"error": "invalid sha256"})
        with db.get_conn() as conn:
            conf = _conf_by_sha(conn, sha256)
        if conf is None:
            return db.send_json(self, 200, {"exists": False})
        db.send_json(self, 200, {"exists": True, "conference": conf})

    def do_POST(self):
        body = db.read_json_body(self)
        url = body.get("url") or ""
        sha256 = (body.get("sha256") or "").lower()
        filename = body.get("filename") or ""

        if not _SHA256_RE.match(sha256):
            return db.send_json(self, 400, {"error": "invalid sha256"})
        if not _blob_url_ok(url):
            return db.send_json(self, 400, {"error": "url must be a Vercel Blob URL"})

        with db.get_conn() as conn:
            # Upload abuse guard (design §6): cache hits are unaffected — only
            # NEW conference creation is limited.
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM conferences WHERE created_at > now() - interval '1 hour'"
                )
                if cur.fetchone()[0] >= 10:
                    return db.send_json(self, 429, {
                        "error": "시간당 신규 업로드 한도(10건)를 초과했습니다. 잠시 후 다시 시도해 주세요."
                    })

            # Claim the hash (idempotent). ON CONFLICT → someone else owns it.
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO conferences (sha256, title, blob_url, status) "
                    "VALUES (%s, %s, %s, 'parsing') "
                    "ON CONFLICT (sha256) DO NOTHING RETURNING id",
                    (sha256, filename or "(untitled)", url),
                )
                row = cur.fetchone()
                conn.commit()

            if row is None:
                existing = _conf_by_sha(conn, sha256)
                if existing and existing["status"] != "failed":
                    return db.send_json(self, 200, {"conference": existing, "cached": True})
                # failed earlier → take over and re-parse
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE conferences SET status='parsing', error=NULL, blob_url=%s "
                        "WHERE sha256=%s AND status='failed' RETURNING id",
                        (url, sha256),
                    )
                    row = cur.fetchone()
                    if row:
                        cur.execute("DELETE FROM records WHERE conf_id=%s", (row[0],))
                    conn.commit()
                if row is None:  # lost the takeover race — treat as cached
                    return db.send_json(self, 200, {"conference": _conf_by_sha(conn, sha256), "cached": True})
            conf_id = row[0]

            try:
                with tempfile.TemporaryDirectory() as td:
                    pdf_path = _download(url, td, filename)
                    actual = _sha256_file(pdf_path)
                    if actual != sha256:
                        raise ValueError("uploaded file hash mismatch")

                    # Heavy imports deferred: keeps GET (cache lookup) cold start light.
                    from core.adapters import load_pdf
                    from core.main import _detect_adapter

                    adapter_mod = _detect_adapter(pdf_path)
                    adapter = adapter_mod.__name__.split(".")[-1] if adapter_mod else "generic"
                    records, meta = load_pdf(pdf_path)

                    if adapter == "generic":
                        # LLM-assisted fallback (M3): once per sha256, fail-soft.
                        from _lib import llmparse
                        from core.adapters.post import normalize_records

                        hint = Path(filename).stem or "unknown conference"
                        llm_records = llmparse.refine_with_llm(pdf_path, hint)
                        if llm_records:
                            records = normalize_records(llm_records)
                            adapter = "llm"

                title = meta.get("event_name") or Path(filename).stem or "(untitled)"
                tz_name = meta.get("event_timezone") or "UTC"
                _derive_times(records, title, tz_name)

                db.insert_records(conn, conf_id, records)
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE conferences SET title=%s, location=%s, tz=%s, adapter=%s, "
                        "status='ready' WHERE id=%s",
                        (title, meta.get("event_location") or "", tz_name, adapter, conf_id),
                    )
                conn.commit()
                db.send_json(self, 200, {
                    "conference": db.fetch_conference(conn, conf_id),
                    "cached": False,
                    "recordCount": len(records),
                })
            except Exception as e:  # mark failed so the UI can show it + allow retry
                conn.rollback()
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE conferences SET status='failed', error=%s WHERE id=%s",
                        (str(e)[:500], conf_id),
                    )
                conn.commit()
                db.send_json(self, 500, {"error": f"parse failed: {e}"})
