"""CLI entry point.

Usage:
    python -m cli.main --pdf <path> --name "<query>" [--threshold 80] [--save]
"""

import argparse
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from core.main import search_pdf


def _parse_args():
    p = argparse.ArgumentParser(description="Search for a name in a conference PDF.")
    p.add_argument("--pdf", required=True, help="Path to the conference program PDF")
    p.add_argument("--name", required=True, help="Name or keyword to search for")
    p.add_argument("--threshold", type=float, default=80.0, help="Fuzzy threshold 0-100 (default 80)")
    p.add_argument("--save", action="store_true", help="Save parsed records to data/sessions/<pdf_stem>.json")
    p.add_argument("--json", action="store_true", dest="as_json", help="Output results as JSON")
    p.add_argument("--export-html", metavar="PATH", help="Export results to a self-contained HTML file")
    p.add_argument("--export-ics", metavar="PATH", help="Export results to an .ics calendar file (UTC, no VTIMEZONE)")
    p.add_argument("--ics", metavar="PATH", help="Export results to an .ics file with VTIMEZONE (preferred)")
    p.add_argument("--text", metavar="PATH", help="Export results to a plain-text file (email-friendly)")
    p.add_argument("--xlsx", metavar="PATH", help="Export results to an .xlsx spreadsheet")
    return p.parse_args()


def main():
    args = _parse_args()
    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"[error] PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[1/3] Parsing {pdf_path.name} ...", file=sys.stderr)
    hits, adapter_name = search_pdf(pdf_path, args.name, threshold=args.threshold)

    event_meta = {}
    if args.save or args.export_html or args.export_ics or args.ics or args.text or args.xlsx:
        from core.main import _detect_adapter
        adapter_mod = _detect_adapter(pdf_path)
        if adapter_mod:
            event_meta = getattr(adapter_mod, "EVENT_META", {})
        if args.save:
            if adapter_mod:
                all_records = adapter_mod.parse(pdf_path)
            else:
                from core.adapters.generic import parse as gp
                all_records = gp(pdf_path)
            out = Path("data/sessions") / (pdf_path.stem + ".json")
            out.parent.mkdir(parents=True, exist_ok=True)
            payload = {**event_meta, "sessions": all_records}
            out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"      -> saved {len(all_records)} records to {out}", file=sys.stderr)

    print(f"      Adapter: {adapter_name}", file=sys.stderr)
    print(f'[2/3] Searching for "{args.name}" (threshold={args.threshold}) ...', file=sys.stderr)
    print(f"      -> {len(hits)} hit(s)", file=sys.stderr)
    print(f"[3/3] Results:", file=sys.stderr)

    if args.export_html:
        from core.exporters.html import export as html_export
        html_export(hits, args.export_html, query=args.name, event_meta=event_meta)
        print(f"      -> HTML saved to {args.export_html}", file=sys.stderr)

    if args.export_ics:
        from core.exporters.ics import export as ics_export
        ics_export(hits, args.export_ics, event_meta=event_meta, query=args.name)
        print(f"      -> ICS saved to {args.export_ics}", file=sys.stderr)

    if args.ics:
        from core.exporters.ics_exporter import export_ics
        export_ics(
            hits,
            event_meta.get("event_timezone", "UTC"),
            args.ics,
            event_name=event_meta.get("event_name", ""),
        )
        print(f"      -> ICS saved to {args.ics}", file=sys.stderr)

    if args.text:
        from core.exporters.text_exporter import export_text
        export_text(
            hits,
            event_meta.get("event_timezone", "UTC"),
            args.text,
            event_name=event_meta.get("event_name", ""),
            event_location=event_meta.get("event_location", ""),
        )
        print(f"      -> text saved to {args.text}", file=sys.stderr)

    if args.xlsx:
        from core.exporters.xlsx_exporter import export_xlsx
        export_xlsx(
            hits,
            event_meta.get("event_timezone", "UTC"),
            args.xlsx,
            event_name=event_meta.get("event_name", ""),
            event_location=event_meta.get("event_location", ""),
            query=args.name,
        )
        print(f"      -> xlsx saved to {args.xlsx}", file=sys.stderr)

    if args.as_json:
        print(json.dumps(hits, ensure_ascii=False, indent=2))
        return

    if not hits:
        print("No matching sessions found.")
        return

    for i, h in enumerate(hits, 1):
        sep = "=" * 62
        print(f"\n{sep}")
        print(f"  Hit #{i}  score={h['_score']}  page={h['page']}")
        print(f"  Date     : {h['date'] or '-'}")
        print(f"  Time     : {h['time'] or '-'}")
        print(f"  Room     : {h['room'] or '-'}")
        code_title = " - ".join(filter(None, [h.get("session_code"), h.get("session_title")]))
        print(f"  Session  : {code_title or '-'}")
        print(f"  Role     : {h['role']}  (is_primary_author={h.get('is_primary_author', False)})")
        print(f"  Person   : {h['person']}")
        if h.get("talk_title"):
            print(f"  Talk     : {h['talk_title'][:120]}")
    print(f"\n{'=' * 62}")


if __name__ == "__main__":
    main()
