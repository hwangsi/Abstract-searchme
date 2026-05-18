"""Diagnostic: superscript author-affiliation mapping across adapters.

Parses PDFs directly (no JSON cache).

Usage:
    python scripts/diag_superscript.py
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import fitz  # PyMuPDF

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.adapters import load_pdf

# ── PDF search paths ──────────────────────────────────────────────────────────
_SEARCH_DIRS = [
    Path("data/pdfs"),
    Path("."),
    Path(".."),
]

_PDF_STEMS = {
    "KCR":  ["KCR2025_Program_Book"],
    "ICR":  ["EN-ICR 2026 f. prog_110526"],
    "GBCC": ["GBCC 2026_AbstractBook"],
}


def _find_pdf(stems: list[str]) -> Path | None:
    for d in _SEARCH_DIRS:
        if not d.exists():
            continue
        for stem in stems:
            p = d / f"{stem}.pdf"
            if p.exists():
                return p
    return None


# ── helpers ───────────────────────────────────────────────────────────────────

_SUPER_MAP = {"0":"0","1":"1","2":"2","3":"3","4":"4","5":"5",
              "6":"6","7":"7","8":"8","9":"9",
              "¹":"1","²":"2","³":"3",
              "⁰":"0","⁴":"4","⁵":"5","⁶":"6",
              "⁷":"7","⁸":"8","⁹":"9"}

def _norm_super(s: str) -> str:
    return "".join(_SUPER_MAP.get(c, c) for c in s)


def _has_superscript_unicode(s: str) -> bool:
    supers = set("¹²³⁰⁴⁵⁶⁷⁸⁹")
    return any(c in supers for c in s)


# ── per-adapter analysis ──────────────────────────────────────────────────────

def analyse(name: str, pdf_path: Path) -> None:
    print(f"\n{'='*65}")
    print(f"Adapter: {name}  |  {pdf_path.name}")
    print("="*65)

    # ── (a) load_pdf + role distribution ─────────────────────────────────────
    print("\n(a) load_pdf() record distribution")
    records, meta = load_pdf(pdf_path)
    role_counts = Counter(r.get("role","?") for r in records)
    print(f"  Total records: {len(records)}")
    for role, cnt in sorted(role_counts.items()):
        print(f"  {role:<15} {cnt:>5}")

    # ── (b) authors_all length distribution ──────────────────────────────────
    print("\n(b) authors_all length distribution (speaker talks)")
    talk_groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in records:
        if r.get("role") == "speaker" and r.get("talk_title","").strip():
            key = (r.get("date",""), r.get("time",""), r.get("room",""), r.get("talk_title",""))
            talk_groups[key].append(r)

    aa_len_dist: Counter = Counter()
    for grp in talk_groups.values():
        aa = grp[0].get("authors_all") or []
        aa_len_dist[len(aa)] += 1
    for l in sorted(aa_len_dist):
        print(f"  {l} author(s): {aa_len_dist[l]} talks")

    # ── (c) speaker affiliation length distribution ───────────────────────────
    print("\n(c) Speaker affiliation field lengths")
    affil_lens = [len(r.get("affiliation","")) for r in records if r.get("role")=="speaker"]
    buckets = Counter()
    for l in affil_lens:
        if l == 0:         buckets["  0 (empty)"] += 1
        elif l <= 60:      buckets[" 1-60 (short/single)"] += 1
        elif l <= 120:     buckets["61-120 (medium)"] += 1
        else:              buckets["120+ (multi-affil combined)"] += 1
    for k in sorted(buckets):
        print(f"  {k}: {buckets[k]}")

    # ── (d/e) raw PDF line-level analysis for superscripts ───────────────────
    print("\n(d)+(e) Raw line samples - searching for affiliation-numbered talks")
    doc = fitz.open(str(pdf_path))

    author_samples: list[tuple[int, str]] = []   # (page, line)
    affil_samples:  list[tuple[int, str]] = []

    # Detect author/affil lines from raw PDF text
    # Author line: contains commas + digits at end of names (KCR pattern)
    # Affil line: starts with digit + space + institution word
    _AFFIL_START = re.compile(r"^[¹²³⁰-⁹\d]\s*[A-Z]")
    _MULTI_AFFIL = re.compile(r"[¹²³⁰-⁹\d]\s+[A-Z].*"
                               r"[¹²³⁰-⁹\d]\s+[A-Z]")
    _AUTHOR_SUPER = re.compile(r"[A-Za-z][¹²³⁰-⁹\d]")
    _AUTHOR_DIGIT = re.compile(r"[A-Za-z]\d(?:,\d)*(?:\s|$|,)")

    for pn in range(min(doc.page_count, 80)):
        lines = [l.strip() for l in doc[pn].get_text().splitlines() if l.strip()]
        for i, line in enumerate(lines):
            # Look for multi-affil lines
            if _MULTI_AFFIL.search(line) and len(affil_samples) < 10:
                affil_samples.append((pn+1, line))
            elif _AFFIL_START.match(line) and len(affil_samples) < 10:
                affil_samples.append((pn+1, line))
            # Look for author lines with superscripts
            if (_AUTHOR_SUPER.search(line) or _AUTHOR_DIGIT.search(line)):
                if "," in line and len(author_samples) < 10:
                    author_samples.append((pn+1, line))
    doc.close()

    print("\n  Author line samples (with superscript indicators):")
    if author_samples:
        for pn, line in author_samples[:10]:
            has_uni = _has_superscript_unicode(line)
            normalized = _norm_super(line)
            print(f"  p{pn}: {line!r}")
            if has_uni:
                print(f"       -> normalized: {normalized!r}")
    else:
        print("  (none found with digit/superscript pattern)")

    print("\n  Affiliation line samples (numbered affilliations):")
    if affil_samples:
        for pn, line in affil_samples[:10]:
            has_uni = _has_superscript_unicode(line)
            print(f"  p{pn}: {line!r}")
    else:
        print("  (none found with numbered affiliation pattern)")

    # ── char-level span size check for superscript detection ─────────────────
    print("\n  Span-size check (looking for smaller font spans near names):")
    doc = fitz.open(str(pdf_path))
    size_samples: list[str] = []
    for pn in range(min(doc.page_count, 60)):
        page = doc[pn]
        blocks = page.get_text("dict")["blocks"]
        for b in blocks:
            if b.get("type") != 0:
                continue
            for line in b["lines"]:
                spans = line["spans"]
                if len(spans) < 2:
                    continue
                # Look for span sequence where text changes size
                for i in range(len(spans)-1):
                    s0, s1 = spans[i], spans[i+1]
                    if (s1["size"] < s0["size"] * 0.75 and
                            s1["text"].strip() and
                            re.match(r"[\d¹²³]", s1["text"].strip()) and
                            len(size_samples) < 5):
                        size_samples.append(
                            f"  p{pn+1}: [{s0['text']!r} size={s0['size']:.1f}] "
                            f"+ [{s1['text']!r} size={s1['size']:.1f}]"
                        )
    doc.close()
    if size_samples:
        print("  Found superscript spans (size drop):")
        for s in size_samples:
            print(s)
    else:
        print("  No size-drop superscript spans found")
        print("  => Superscripts likely encoded as inline text chars")

    # ── summary ───────────────────────────────────────────────────────────────
    has_author_super = len(author_samples) > 0
    has_affil_numbered = len(affil_samples) > 0
    print(f"\n  SUMMARY for {name}:")
    print(f"  Author superscripts detected: {'YES' if has_author_super else 'NO'}")
    print(f"  Numbered affiliations detected: {'YES' if has_affil_numbered else 'NO'}")
    if has_author_super and author_samples:
        sample_line = author_samples[0][1]
        if _has_superscript_unicode(sample_line):
            print("  Superscript format: Unicode (e.g. Choi¹)")
        else:
            print("  Superscript format: ASCII digits inline (e.g. Choi1)")


def main():
    found_any = False
    for name, stems in _PDF_STEMS.items():
        pdf = _find_pdf(stems)
        if pdf:
            analyse(name, pdf)
            found_any = True
        else:
            print(f"\n{name}: PDF not found (stems: {stems}) - skipping")

    if not found_any:
        print("\nNo PDFs found. Place PDFs in data/pdfs/ or project root.")


if __name__ == "__main__":
    main()
