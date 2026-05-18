"""Adapter package. Public entry point: load_pdf().

All callers (GUI worker, CLI, tests) should use load_pdf() rather than
calling adapter.parse() directly, so that normalize_records() is always
applied exactly once.
"""

from __future__ import annotations

from pathlib import Path


def load_pdf(pdf_path: str | Path) -> tuple[list[dict], dict]:
    """Detect adapter, parse PDF, normalize records.

    Returns:
        (records, event_meta)  — records satisfy invariants I1-I5.
    """
    from core.main import _detect_adapter, _wrap_generic
    from core.adapters.generic import parse as _generic_parse
    from core.adapters.post import normalize_records

    pdf_path = Path(pdf_path)
    adapter = _detect_adapter(pdf_path)
    if adapter is not None:
        records = adapter.parse(pdf_path)
        event_meta = getattr(adapter, "EVENT_META", {})
    else:
        records = _wrap_generic(_generic_parse(pdf_path))
        event_meta = {}

    return normalize_records(records), event_meta
