"""One-shot diagnostic: KCR adapter affiliation fill-rate and role distribution.

Usage:
    python scripts/diag_kcr_affiliation.py
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.adapters import kcr

PDF = Path("data/pdfs/KCR2025_Program_Book.pdf")
JSON_CACHE = Path("data/sessions/KCR2025_Program_Book.json")

if PDF.exists():
    print("Parsing KCR PDF …")
    records = kcr.parse(PDF)
elif JSON_CACHE.exists():
    import json
    print(f"PDF not found - loading cached JSON: {JSON_CACHE}")
    with open(JSON_CACHE, encoding="utf-8") as f:
        data = json.load(f)
    records = data.get("sessions", data) if isinstance(data, dict) else data
else:
    sys.exit(f"Neither PDF ({PDF}) nor JSON cache ({JSON_CACHE}) found.")

print(f"Total records: {len(records)}\n")

# ── (a) role distribution ────────────────────────────────────────────────────
role_counts = Counter(r["role"] for r in records)
print("(a) Role distribution")
print("-" * 40)
for role, cnt in sorted(role_counts.items()):
    print(f"  {role:<15} {cnt:>5} records")
print()

# ── (b) affiliation fill rate by role ────────────────────────────────────────
by_role: dict[str, list[dict]] = defaultdict(list)
for r in records:
    by_role[r["role"]].append(r)

print("(b) Affiliation fill rate by role")
print("-" * 40)
for role in sorted(by_role):
    recs = by_role[role]
    filled = sum(1 for r in recs if r.get("affiliation", "").strip())
    pct = 100 * filled / len(recs) if recs else 0
    print(f"  {role:<15}  {filled}/{len(recs)} filled  ({pct:.1f}%)")
print()

# ── (c) speaker sample (10 records) ─────────────────────────────────────────
speakers = by_role.get("speaker", [])
print(f"(c) Speaker sample (first 10 of {len(speakers)})")
print("-" * 60)
for r in speakers[:10]:
    print(f"  page={r['page']}  person={r['person']!r}")
    print(f"    affiliation={r['affiliation']!r}")
    print(f"    talk_title ={r['talk_title']!r}")
print()

# ── (d) "Seoul National" token in affiliation — by role ──────────────────────
TOKEN = "Seoul National"
TOKEN_lower = TOKEN.lower()
print(f'(d) Records with "{TOKEN}" in affiliation, by role')
print("-" * 60)
matched: dict[str, list[str]] = defaultdict(list)
for r in records:
    affil = r.get("affiliation", "")
    if TOKEN_lower in affil.lower():
        matched[r["role"]].append(r["person"])

if not matched:
    print('  (none found — affiliation field is empty for all relevant roles)')
else:
    for role in sorted(matched):
        print(f"  {role}: {len(matched[role])} hits")
        for p in matched[role][:5]:
            print(f"    {p}")
        if len(matched[role]) > 5:
            print(f"    … +{len(matched[role]) - 5} more")
print()

# ── diagnosis summary ────────────────────────────────────────────────────────
speaker_affil_pct = 0.0
if speakers:
    filled = sum(1 for r in speakers if r.get("affiliation", "").strip())
    speaker_affil_pct = 100 * filled / len(speakers)

print("=" * 60)
print("DIAGNOSIS")
print("=" * 60)
if speaker_affil_pct < 5:
    print("H1 CONFIRMED: speaker affiliation fill rate is near 0%.")
    print("  → KCR adapter emits speaker records with affiliation=''.")
elif speaker_affil_pct < 50:
    print("H1 LIKELY (partial): many speaker affiliations are empty.")
    print("  → Check H2 (normalisation) as a secondary factor.")
else:
    print("H1 RULED OUT: speaker affiliation fill rate is high.")
    print("  → Likely H2 (normalisation) or H3 (missing records).")
