"""Export search results to a self-contained HTML file."""

from __future__ import annotations
import html as _html
from pathlib import Path
from typing import Any

_CSS = """
body{font-family:Arial,sans-serif;max-width:960px;margin:24px auto;padding:0 16px;color:#222}
h1{font-size:1.3em;border-bottom:2px solid #333;padding-bottom:8px;margin-bottom:4px}
p.meta{color:#555;font-size:.9em;margin:0 0 14px}
table{border-collapse:collapse;width:100%;font-size:.88em}
th{background:#333;color:#fff;padding:8px 10px;text-align:left;white-space:nowrap}
td{padding:7px 10px;border-bottom:1px solid #ddd;vertical-align:top}
tr:nth-child(even) td{background:#f7f7f7}
.chair{color:#0055cc;font-weight:bold}
.speaker{color:#007700;font-weight:bold}
.discussant{color:#884400;font-weight:bold}
.score{color:#999;font-size:.82em}
small{color:#666}
"""

_COLS = ["#", "Date", "Time", "Room", "Session", "Role", "Person / Affiliation", "Talk Title", "Score"]


def _esc(v: Any) -> str:
    return _html.escape(str(v or ""))


def _row(i: int, h: dict[str, Any]) -> str:
    code_title = " – ".join(filter(None, [h.get("session_code"), h.get("session_title")]))
    role = h.get("role", "unknown")
    role_cls = role if role in ("chair", "speaker", "discussant") else ""
    person = _esc(h.get("person", ""))
    if h.get("affiliation"):
        person += f"<br><small>{_esc(h['affiliation'])}</small>"
    cells = [
        str(i),
        _esc(h.get("date")) or "–",
        _esc(h.get("time")) or "–",
        _esc(h.get("room")) or "–",
        _esc(code_title) or "–",
        f'<span class="{role_cls}">{_esc(role)}</span>',
        person or "–",
        _esc(h.get("talk_title")),
        f'<span class="score">{h.get("_score", "")}</span>',
    ]
    return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>\n"


def export(
    hits: list[dict[str, Any]],
    output_path: "Path | str",
    query: str = "",
    event_meta: "dict[str, Any] | None" = None,
) -> None:
    event_meta = event_meta or {}
    event_name = event_meta.get("event_name", "")
    title = f"Search: {query}"
    if event_name:
        title += f" — {event_name}"

    header_cells = "".join(f"<th>{c}</th>" for c in _COLS)
    rows = "".join(_row(i, h) for i, h in enumerate(hits, 1))

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>{_esc(title)}</h1>
<p class="meta">{len(hits)} result(s)</p>
<table>
<thead><tr>{header_cells}</tr></thead>
<tbody>
{rows}</tbody>
</table>
</body>
</html>"""
    Path(output_path).write_text(page, encoding="utf-8")
