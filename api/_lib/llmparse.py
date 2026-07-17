"""LLM-assisted fallback parser for conferences without a dedicated adapter.

Provider-agnostic: any OpenAI-compatible chat-completions endpoint via
  LLM_API_KEY   (required to enable)
  LLM_BASE_URL  (default: Groq)
  LLM_MODEL     (default: llama-3.3-70b-versatile)

Design (설계서 M3): runs ONLY when adapter == 'generic'; selects program-like
pages (dense with HH:MM-HH:MM ranges) instead of feeding the whole PDF;
one PDF is processed once per sha256 (parse.py is idempotent), so cost/rate
stays trivial. Fail-soft: any error returns None and the generic records
stand.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

_TIME_RANGE_RE = re.compile(r"\b\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}\b")

MAX_PAGES = 20          # LLM calls per PDF (1 page per call)
MAX_PAGE_CHARS = 7000
TIME_BUDGET_SEC = 150   # parse.py has maxDuration 300 — leave room for the rest

_SYSTEM_PROMPT = """You extract conference program sessions from raw PDF page text.
Reply with strict JSON only: {"records": [ ... ]} — no commentary.
Each record = one (person, role, talk/session) participation with fields:
  "date": date as printed; MUST keep the English month name and day (e.g. "May 14" or "Sep. 26 (Fri)"); "" if absent on this page
  "time": "HH:MM-HH:MM" ("" if absent)
  "room": room/hall name ("" if absent)
  "session_code": short code like "SS 09" ("" if none)
  "session_title": session name ("" if none)
  "role": one of "chair" | "speaker" | "discussant" | "moderator" | "panelist"
  "person": one full person name (make one record per person)
  "affiliation": that person's institution ("" if not printed)
  "talk_title": individual talk/lecture title ("" for chairs/session-level roles)
  "is_primary_author": true only for the presenting speaker of a talk
  "authors_all": array of all author names of that talk ([] if not printed)
Rules: every listed chair/moderator/speaker/discussant/panelist gets a record.
Do not invent data not present in the text. Keep names exactly as printed."""


def llm_configured() -> bool:
    return bool(os.environ.get("LLM_API_KEY"))


def _chat(page_text: str, event_hint: str, deadline: float) -> list[dict]:
    """One extraction call with 429/5xx retry (free tiers throttle by
    tokens/minute — honoring Retry-After is what makes full coverage work)."""
    base = (os.environ.get("LLM_BASE_URL") or "https://api.groq.com/openai/v1").rstrip("/")
    model = os.environ.get("LLM_MODEL") or "llama-3.3-70b-versatile"
    payload = json.dumps({
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Conference: {event_hint}\n\nPDF page text:\n{page_text}"},
        ],
    }).encode("utf-8")

    while True:
        req = urllib.request.Request(
            base + "/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {os.environ['LLM_API_KEY']}",
                # Groq sits behind Cloudflare, which 403s urllib's default UA (code 1010)
                "User-Agent": "abstract-searcher/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                out = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503):
                raise
            wait = min(float(e.headers.get("Retry-After") or 10), 60.0)
            if time.time() + wait > deadline:
                raise
            time.sleep(wait)

    content = out["choices"][0]["message"]["content"]
    records = json.loads(content).get("records") or []
    return records if isinstance(records, list) else []


def _select_pages(pdf_path) -> list[tuple[int, str]]:
    """Pages that look like program listings: >=3 time ranges on the page."""
    import fitz

    picked = []
    with fitz.open(str(pdf_path)) as doc:
        for i, page in enumerate(doc):
            text = page.get_text()
            if len(_TIME_RANGE_RE.findall(text)) >= 3:
                picked.append((i + 1, text[:MAX_PAGE_CHARS]))
            if len(picked) >= MAX_PAGES:
                break
    return picked


_ROLES = {"chair", "speaker", "discussant", "moderator", "panelist"}


def _clean(rec: dict, page_no: int) -> dict | None:
    person = str(rec.get("person") or "").strip()
    if not person or len(person) > 120:
        return None
    role = str(rec.get("role") or "").strip().lower()
    s = lambda k: str(rec.get(k) or "").strip()
    return {
        "page": page_no,
        "date": s("date"),
        "time": s("time"),
        "room": s("room"),
        "session_code": s("session_code"),
        "session_title": s("session_title"),
        "role": role if role in _ROLES else "speaker",
        "is_primary_author": bool(rec.get("is_primary_author")),
        "person": person,
        "affiliation": s("affiliation"),
        "talk_title": s("talk_title"),
        "authors_all": [str(a).strip() for a in (rec.get("authors_all") or []) if str(a).strip()][:30],
    }


def refine_with_llm(pdf_path, event_hint: str, stats: dict | None = None) -> list[dict] | None:
    """Return extracted records, or None on any failure / nothing found.
    Pass a dict as `stats` to receive {pages, ok, failed, lastError}."""
    if not llm_configured():
        return None
    st = stats if stats is not None else {}
    try:
        pages = _select_pages(pdf_path)
        st.update(pages=len(pages), ok=0, failed=0, lastError="")
        if not pages:
            return None
        deadline = time.time() + TIME_BUDGET_SEC
        out: list[dict] = []
        for page_no, text in pages:
            if time.time() > deadline:
                st["lastError"] = "time budget exhausted"
                break
            try:
                for rec in _chat(text, event_hint, deadline):
                    cleaned = _clean(rec, page_no)
                    if cleaned:
                        out.append(cleaned)
                st["ok"] += 1
            except Exception as e:  # one bad page/call must not kill the rest
                st["failed"] += 1
                st["lastError"] = repr(e)[:200]
        return out or None
    except Exception as e:
        st["lastError"] = repr(e)[:200]
        return None
