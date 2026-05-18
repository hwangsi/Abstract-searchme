"""Auto-detect adapter from PDF metadata/filename and run search."""

from __future__ import annotations
import re
from pathlib import Path
import fitz

from core.adapters import kcr, icr, gbcc
from core.adapters.generic import parse as generic_parse
from core.adapters.post import normalize_records
from core.search.matcher import matches


def _detect_adapter(pdf_path: Path):
    """Return the adapter module (not just parse fn) or None for generic."""
    stem = pdf_path.stem.lower()
    if "kcr" in stem or "korean congress" in stem:
        return kcr
    if "icr" in stem or "en-icr" in stem:
        return icr
    if "gbcc" in stem or "global breast cancer" in stem:
        return gbcc

    # Check PDF metadata
    try:
        doc = fitz.open(str(pdf_path))
        meta = doc.metadata
        doc.close()
        creator = (meta.get("creator") or "").lower()
        title = (meta.get("title") or "").lower()
        if "kcr" in title or "korean congress" in title:
            return kcr
        if "icr" in title:
            return icr
        if "gbcc" in title or "global breast cancer" in title:
            return gbcc
        if "corel" in creator:
            return icr  # CorelDRAW = ICR-style visual layout
    except Exception:
        pass

    return None  # fallback to generic


def search_pdf(
    pdf_path: str | Path,
    query: str,
    threshold: float = 80.0,
    adapter_module=None,
) -> tuple[list[dict], str]:
    """Parse pdf_path and return (hits, adapter_name)."""
    pdf_path = Path(pdf_path)
    if adapter_module is None:
        adapter_module = _detect_adapter(pdf_path)
    if adapter_module is not None:
        adapter_name = adapter_module.__name__.split(".")[-1]
        records = adapter_module.parse(pdf_path)
    else:
        adapter_name = "generic"
        records = generic_parse(pdf_path)
        records = _wrap_generic(records)

    records = normalize_records(records)
    hits = matches(query, records, threshold=threshold)
    return hits, adapter_name


def _wrap_generic(sessions: list[dict]) -> list[dict]:
    """Convert generic session dicts into role-record format."""
    out = []
    for s in sessions:
        out.append({
            "page": s.get("page", 0),
            "date": "",
            "time": s.get("time", ""),
            "room": "",
            "session_code": s.get("code", ""),
            "session_title": s.get("title", ""),
            "role": "unknown",
            "is_primary_author": False,
            "person": s.get("title", "") + " " + s.get("body", ""),
            "affiliation": "",
            "talk_title": "",
        })
    return out
