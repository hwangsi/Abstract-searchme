"""Apply db/schema.sql to the Neon database.

Usage:
    set DATABASE_URL=postgres://...   (or $env:DATABASE_URL / export)
    python scripts/init_webdb.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL is not set", file=sys.stderr)
        return 1
    schema = (Path(__file__).resolve().parent.parent / "db" / "schema.sql").read_text(encoding="utf-8")
    with psycopg.connect(url) as conn:
        conn.execute(schema)
        conn.commit()
    print("schema applied OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
