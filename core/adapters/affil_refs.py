"""Shared helpers for superscript-based author-to-affiliation mapping.

KCR PDF format (confirmed by diagnostic on 2026-05-19):
  - Author line: 'Name1, Name2, Name3'   (digit directly after name, no space)
  - Affil line:  '1AffiliationA, 2AffiliationB'  (digit directly before uppercase)
  - Email:       on a separate line, or inline after the last affil entry

Unicode superscript chars (e.g. 'Choi¹') are treated the same as
ASCII digits appended to names; both are normalised to ASCII before parsing.
"""

from __future__ import annotations

import re

# ── Unicode superscript normalisation ────────────────────────────────────────

_SUPERSCRIPT_MAP: dict[str, str] = {
    '¹': '1', '²': '2', '³': '3',
    '⁰': '0', '⁴': '4', '⁵': '5', '⁶': '6',
    '⁷': '7', '⁸': '8', '⁹': '9',
}


def normalize_superscripts(s: str) -> str:
    """Replace Unicode superscript digits with plain ASCII digits."""
    for k, v in _SUPERSCRIPT_MAP.items():
        s = s.replace(k, v)
    return s


# ── author token parser ───────────────────────────────────────────────────────

def parse_author_with_refs(token: str) -> tuple[str, list[int]]:
    """Extract a clean author name and its affiliation reference numbers.

    Examples:
        'Joon-Il Choi1'   -> ('Joon-Il Choi', [1])
        'Kim2,3'          -> ('Kim', [2, 3])
        'Chang Hee Lee'   -> ('Chang Hee Lee', [])
        'Seo Yeon Youn²' -> ('Seo Yeon Youn', [2])
    """
    token = normalize_superscripts(token.strip())
    # Match: name body + optional space + trailing digit(s)/comma sequence
    m = re.match(r'^(.*?)\s*(\d[\d,\s]*)$', token)
    if m:
        name = m.group(1).strip()
        refs = [int(x) for x in re.findall(r'\d+', m.group(2))]
        if refs and name:
            return name, refs
    return token, []


# ── affiliation block parser ──────────────────────────────────────────────────

_EMAIL_RE = re.compile(r'\s*[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')


def parse_affil_dict(raw: str) -> dict[int, str]:
    """Parse a numbered affiliation block into {num: text}.

    Input examples:
        '1AffiliationA, 2AffiliationB'
        '1AffiliationA, Korea, 2AffiliationB, Korea.'

    Splitting rule: a comma followed by digit(s) immediately before an
    uppercase letter marks the start of the next numbered entry.  This
    deliberately does NOT split on street numbers like '100 Daehak-ro'
    because those have a *space* between the digit and the letter.

    Returns {} when the line contains no numbered entries (single-affil
    case where the full string applies to all authors).
    """
    raw = _EMAIL_RE.sub('', raw).strip().rstrip('.')
    if not raw:
        return {}

    # Split at boundary: ',<optional-space><digit(s)><UPPERCASE>'
    parts = re.split(r',\s*(?=\d+[A-Z])', raw)

    result: dict[int, str] = {}
    for part in parts:
        part = part.strip()
        m = re.match(r'^(\d+)([A-Z].*)', part)
        if m:
            num = int(m.group(1))
            affil = m.group(2).strip().rstrip(',').strip()
            result[num] = affil

    return result


# ── resolver ─────────────────────────────────────────────────────────────────

def resolve_affil(
    refs: list[int],
    affil_dict: dict[int, str],
    fallback: str = '',
) -> str:
    """Map an author's reference numbers to an affiliation string.

    Args:
        refs:       Reference numbers from the author's superscript(s).
        affil_dict: {num: text} from parse_affil_dict().
        fallback:   Affiliation string to use when affil_dict is empty
                    (single-affil format with no numbered entries).

    Returns:
        Resolved affiliation string, or '' if ambiguous.
    """
    if not affil_dict:
        # No numbered entries: single affiliation applies to all authors.
        return fallback
    if refs:
        parts = [affil_dict[r] for r in refs if r in affil_dict]
        return '; '.join(parts) if parts else ''
    else:
        # Author carries no superscript.
        if len(affil_dict) == 1:
            return next(iter(affil_dict.values()))
        return ''  # multiple affiliations, can't determine which
