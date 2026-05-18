"""Extract text blocks with coordinates from a PDF using PyMuPDF."""

from pathlib import Path
from typing import Iterator
import fitz  # pymupdf


def extract_pages(pdf_path: str | Path) -> Iterator[dict]:
    """Yield one dict per page with page number, raw text, and block list.

    Each block: {"bbox": (x0,y0,x1,y1), "text": str, "page": int}
    """
    doc = fitz.open(str(pdf_path))
    try:
        for page_num, page in enumerate(doc, start=1):
            blocks = []
            for block in page.get_text("blocks"):
                x0, y0, x1, y1, text, *_ = block
                text = text.strip()
                if text:
                    blocks.append({"bbox": (x0, y0, x1, y1), "text": text, "page": page_num})
            yield {"page": page_num, "blocks": blocks}
    finally:
        doc.close()


def extract_lines(pdf_path: str | Path) -> list[dict]:
    """Return all non-empty text lines with page number and y-coordinate."""
    lines = []
    for page_data in extract_pages(pdf_path):
        for block in page_data["blocks"]:
            for raw_line in block["text"].splitlines():
                raw_line = raw_line.strip()
                if raw_line:
                    lines.append({
                        "page": block["page"],
                        "y": block["bbox"][1],
                        "text": raw_line,
                    })
    return lines
