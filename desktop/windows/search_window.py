"""Window 2: 검색 창 — 5b 플레이스홀더, 5c에서 완성."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class SearchWindow(QWidget):
    """Window 2: 이름/소속 검색 (5c에서 완성)."""

    back_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Abstract Searcher")
        self.setMinimumSize(700, 520)
        self._records: list = []
        self._event_meta: dict = {}
        self._pdf_path: Path | None = None
        self._setup_ui()

    # ── 공개 API ──────────────────────────────────────────────────────────────

    def load(self, records: list, event_meta: dict, pdf_path: Path) -> None:
        """새 PDF 파싱 결과를 불러온다."""
        self._records    = records
        self._event_meta = event_meta
        self._pdf_path   = pdf_path
        self._refresh_header()

    # ── UI 구성 ───────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        self._header = QLabel()
        self._header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._header.setWordWrap(True)
        self._header.setStyleSheet("font-size: 15px; color: #1a1a2e;")
        layout.addWidget(self._header)

        layout.addStretch()

        btn_back = QPushButton("← 다른 PDF 열기")
        btn_back.setFixedWidth(180)
        btn_back.setStyleSheet(
            "QPushButton {"
            "  background: #f0f2f5; color: #333;"
            "  border: 1px solid #ccc; border-radius: 6px;"
            "  font-size: 13px; padding: 7px 14px;"
            "}"
            "QPushButton:hover { background: #e2e6ea; }"
        )
        btn_back.clicked.connect(self.back_clicked)
        layout.addWidget(btn_back, alignment=Qt.AlignmentFlag.AlignLeft)

    def _refresh_header(self) -> None:
        name = (
            self._event_meta.get("event_name")
            or (self._pdf_path.name if self._pdf_path else "")
        )
        location = self._event_meta.get("event_location", "")
        tz       = self._event_meta.get("event_timezone", "")
        meta     = " — ".join(filter(None, [location, f"({tz})" if tz else ""]))
        header   = f"{name}  {meta}" if meta else name

        self._header.setText(
            f"<b>{header}</b><br><br>"
            f"{len(self._records):,}건 파싱됨<br><br>"
            "<span style='color:#aaa'>검색 UI는 5c에서 구현됩니다.</span>"
        )
