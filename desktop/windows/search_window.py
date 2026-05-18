"""
desktop/windows/search_window.py

Stage 5c: Window 2 — search + result cards + TXT/XLSX/ICS export.

Receives parsed records from UploadWindow via:
    upload_window.ready.connect(search_window.load)

Renders one SessionCard per match from core.search.matcher.matches(),
and exports the current result set via the three core.exporters
functions.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import difflib
from collections import defaultdict

from core.search.matcher import matches, matches_affiliation

# NOTE: adjust these three imports to match your actual exporter module
# names if they differ (e.g. core.exporters.text vs core.exporters.text_exporter).
from core.exporters.text_exporter import export_text
from core.exporters.xlsx_exporter import export_xlsx
from core.exporters.ics_exporter import export_ics


# ---------------------------------------------------------------------------
# role display
# ---------------------------------------------------------------------------

ROLE_LABEL = {
    "speaker": "발표자",
    "chair": "좌장",
    "discussant": "토론자",
    "panelist": "패널",
}

ROLE_COLOR = {
    "speaker": "#1e6fbf",       # blue
    "chair": "#2c7a3e",         # green
    "discussant": "#c2671a",    # orange
    "panelist": "#7b2d8b",      # purple
}


def _sanitize_filename(name: str) -> str:
    """Strip characters Windows refuses in filenames."""
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "schedule"


def _find_bold_author(person: str, authors_all: list[str]) -> str:
    """Return the entry in authors_all that best matches person (exact first, then fuzzy)."""
    if not person or not authors_all:
        return ''
    if person in authors_all:
        return person
    matches_close = difflib.get_close_matches(person, authors_all, n=1, cutoff=0.6)
    return matches_close[0] if matches_close else ''


def _group_affil_results(hits: list[dict]) -> list[dict]:
    """Collapse per-author affiliation hits into one card per talk.

    Speaker records for the same talk are merged: the highest-scoring record
    is kept as representative and a 'matched_persons' list is attached so
    the card can bold every matched author.  Non-speaker records (chairs,
    discussants, panelists) are kept as individual entries.
    """
    talk_groups: dict[tuple, list[dict]] = defaultdict(list)
    ungrouped: list[dict] = []

    for h in hits:
        talk_title = (h.get("talk_title") or "").strip()
        if h.get("role") == "speaker" and talk_title:
            key = (h.get("date", ""), h.get("time", ""), h.get("room", ""), talk_title)
            talk_groups[key].append(h)
        else:
            ungrouped.append(h)

    result: list[dict] = []
    for group in talk_groups.values():
        rep = dict(max(group, key=lambda h: h.get("_score", 0)))
        rep["matched_persons"] = [h["person"] for h in group]
        result.append(rep)

    result.extend(ungrouped)
    result.sort(key=lambda h: -h.get("_score", 0))
    return result


# ---------------------------------------------------------------------------
# SessionCard
# ---------------------------------------------------------------------------

class SessionCard(QFrame):
    """One result card for a single matched record."""

    def __init__(self, record: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("SessionCard")
        self.setStyleSheet("""
            #SessionCard {
                background-color: #ffffff;
                border: 1px solid #d0d0d0;
                border-radius: 6px;
                font-size: 14pt;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        # --- top row: role badge + date·time + (1저자 표시) -----------------
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        role = (record.get("role") or "").lower()
        role_text = ROLE_LABEL.get(role, role or "—")
        role_color = ROLE_COLOR.get(role, "#666666")

        badge = QLabel(role_text)
        badge.setStyleSheet(f"""
            background-color: {role_color};
            color: white;
            padding: 2px 10px;
            border-radius: 10px;
            font-weight: bold;
        """)
        badge.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        top_row.addWidget(badge)

        date = record.get("date") or ""
        time = record.get("time") or ""
        when = " · ".join(x for x in (date, time) if x)
        when_label = QLabel(when)
        wf = QFont()
        wf.setBold(True)
        when_label.setFont(wf)
        top_row.addWidget(when_label)

        top_row.addStretch()

        matched_set = set(record.get("matched_persons") or [])
        authors_all_check: list[str] = record.get("authors_all") or []
        is_primary = record.get("is_primary_author") or (
            bool(matched_set) and bool(authors_all_check) and authors_all_check[0] in matched_set
        )
        if is_primary:
            primary = QLabel("★ 1저자")
            primary.setStyleSheet("color: #c97b00; font-weight: bold;")
            top_row.addWidget(primary)

        layout.addLayout(top_row)

        # --- room ------------------------------------------------------------
        room = record.get("room") or ""
        if room:
            room_label = QLabel(f"📍 {room}")
            room_label.setStyleSheet("color: #444444;")
            layout.addWidget(room_label)

        # --- session code + title -------------------------------------------
        session_code = record.get("session_code") or ""
        session_title = record.get("session_title") or ""
        session_parts = [p for p in (session_code, session_title) if p]
        if session_parts:
            session_label = QLabel(" — ".join(session_parts))
            session_label.setWordWrap(True)
            session_label.setStyleSheet("color: #222222; font-weight: 500;")
            layout.addWidget(session_label)

        # --- talk title (mostly for speakers) -------------------------------
        talk_title = record.get("talk_title") or ""
        if talk_title:
            talk_label = QLabel(f"🎤 {talk_title}")
            talk_label.setWordWrap(True)
            talk_label.setStyleSheet("color: #333333;")
            layout.addWidget(talk_label)

        # --- footer: full author list (bolded: all matched persons) ---------
        person = record.get("person") or ""
        authors_all: list[str] = record.get("authors_all") or []
        matched_persons: list[str] = record.get("matched_persons") or []
        display_authors = authors_all if authors_all else ([person] if person else [])

        if display_authors:
            if matched_persons:
                bold_set = set(matched_persons)
            else:
                single = _find_bold_author(person, display_authors)
                bold_set = {single} if single else set()
            parts = []
            for a in display_authors:
                parts.append(f'<b>{a}</b>' if a in bold_set else a)
            authors_label = QLabel(', '.join(parts))
            authors_label.setTextFormat(Qt.RichText)
            authors_label.setWordWrap(True)
            authors_label.setStyleSheet("color: #555555;")
            layout.addWidget(authors_label)

        # --- footer: affiliation --------------------------------------------
        affiliation = record.get("affiliation") or ""
        if affiliation:
            affil_label = QLabel(affiliation)
            affil_label.setStyleSheet("color: #888888;")
            affil_label.setWordWrap(True)
            layout.addWidget(affil_label)

        # --- meta: page · match score ---------------------------------------
        page = record.get("page")
        score = record.get("_score")
        meta_bits: list[str] = []
        if page is not None:
            meta_bits.append(f"p.{page}")
        if score is not None:
            try:
                meta_bits.append(f"match {float(score):.0f}")
            except (TypeError, ValueError):
                pass
        if meta_bits:
            meta_label = QLabel(" · ".join(meta_bits))
            meta_label.setAlignment(Qt.AlignRight)
            meta_label.setStyleSheet("color: #aaaaaa; font-size: 11pt;")
            layout.addWidget(meta_label)


# ---------------------------------------------------------------------------
# SearchWindow
# ---------------------------------------------------------------------------

class SearchWindow(QWidget):
    """Window 2: search input + result cards + export bar."""

    back_requested = Signal()  # emitted when user clicks "다시 열기"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # data state
        self._records: list[dict] = []
        self._event_meta: dict = {}
        self._pdf_path: Optional[Path] = None
        self._current_results: list[dict] = []
        self._current_query: str = ""

        self.setWindowTitle("Abstract Searcher")
        self.resize(760, 760)

        self._build_ui()

    # -- UI ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_search_bar())
        root.addWidget(self._build_count_bar())
        root.addWidget(self._build_results_area(), 1)
        root.addWidget(self._build_export_bar())

    def _build_header(self) -> QWidget:
        bar = QFrame()
        bar.setStyleSheet(
            "background-color: #f4f5f7; border-bottom: 1px solid #d8d8d8;"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 10, 12, 10)

        self.back_btn = QPushButton("← 다시 열기")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(self.back_requested.emit)
        layout.addWidget(self.back_btn)

        layout.addSpacing(8)

        self.event_label = QLabel("")
        ef = QFont()
        ef.setBold(True)
        self.event_label.setFont(ef)
        layout.addWidget(self.event_label)

        layout.addStretch()

        self.pdf_label = QLabel("")
        self.pdf_label.setStyleSheet("color: #666666;")
        layout.addWidget(self.pdf_label)

        return bar

    def _build_search_bar(self) -> QWidget:
        bar = QFrame()
        bar.setStyleSheet(
            "background-color: #ffffff; border-bottom: 1px solid #e0e0e0;"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._radio_name = QRadioButton("이름으로")
        self._radio_affil = QRadioButton("소속으로")
        self._radio_name.setChecked(True)

        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self._radio_name, 0)
        self._mode_group.addButton(self._radio_affil, 1)
        self._mode_group.idClicked.connect(self._on_mode_changed)

        layout.addWidget(self._radio_name)
        layout.addWidget(self._radio_affil)
        layout.addSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("예: Sung Hwang / 홍길동")
        self.search_input.returnPressed.connect(self._on_search)
        self.search_input.textChanged.connect(self._on_query_changed)
        layout.addWidget(self.search_input, 1)

        self.search_btn = QPushButton("검색")
        self.search_btn.setDefault(True)
        self.search_btn.setEnabled(False)
        self.search_btn.clicked.connect(self._on_search)
        layout.addWidget(self.search_btn)

        return bar

    def _build_count_bar(self) -> QWidget:
        bar = QFrame()
        bar.setStyleSheet(
            "background-color: #fafafa; border-bottom: 1px solid #ececec;"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 8, 14, 8)

        self.count_label = QLabel("이름을 입력하고 검색하세요.")
        self.count_label.setStyleSheet("color: #555555;")
        layout.addWidget(self.count_label)
        layout.addStretch()

        return bar

    def _build_results_area(self) -> QWidget:
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background-color: #f0f0f2; border: none;")

        self.results_container = QWidget()
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setContentsMargins(14, 14, 14, 14)
        self.results_layout.setSpacing(10)
        self.results_layout.addStretch()  # cards stack from top

        self.scroll.setWidget(self.results_container)
        return self.scroll

    def _build_export_bar(self) -> QWidget:
        bar = QFrame()
        bar.setStyleSheet(
            "background-color: #f4f5f7; border-top: 1px solid #d8d8d8;"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        layout.addStretch()

        self.txt_btn = QPushButton("TXT 저장")
        self.txt_btn.clicked.connect(self._on_export_txt)
        layout.addWidget(self.txt_btn)

        self.xlsx_btn = QPushButton("XLSX 저장")
        self.xlsx_btn.clicked.connect(self._on_export_xlsx)
        layout.addWidget(self.xlsx_btn)

        self.ics_btn = QPushButton("ICS 저장")
        self.ics_btn.clicked.connect(self._on_export_ics)
        layout.addWidget(self.ics_btn)

        self._set_export_enabled(False)

        return bar

    # -- public API ----------------------------------------------------------

    def load(self, records: list[dict], event_meta: dict, pdf_path: Path) -> None:
        """Called by UploadWindow.ready signal after parsing succeeds."""
        self._records = records or []
        self._event_meta = event_meta or {}
        self._pdf_path = Path(pdf_path) if pdf_path else None

        self.event_label.setText(self._event_meta.get("event_name", "") or "")
        self.pdf_label.setText(self._pdf_path.name if self._pdf_path else "")

        # reset search state
        self.search_input.clear()
        self.search_input.setFocus()
        self._clear_results()
        self.count_label.setText(
            f"총 {len(self._records)}개 레코드 로드됨. 이름을 입력하고 검색하세요."
        )
        self._current_results = []
        self._current_query = ""
        self._set_export_enabled(False)

    # -- handlers ------------------------------------------------------------

    def _on_query_changed(self, text: str) -> None:
        self.search_btn.setEnabled(bool(text.strip()))

    def _on_mode_changed(self, mode_id: int) -> None:
        if mode_id == 0:
            self.search_input.setPlaceholderText("예: Sung Hwang / 홍길동")
            self.count_label.setText("이름을 입력하고 검색하세요.")
        else:
            self.search_input.setPlaceholderText("예: Seoul National / Bundang / SNUBH")
            self.count_label.setText("소속을 입력하고 검색하세요.")
        self._clear_results()
        self._current_results = []
        self._set_export_enabled(False)

    def _on_search(self) -> None:
        query = self.search_input.text().strip()
        if not query:
            return
        if not self._records:
            QMessageBox.warning(self, "검색 불가", "로드된 레코드가 없습니다.")
            return

        mode = self._mode_group.checkedId()  # 0 = name, 1 = affiliation

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            try:
                if mode == 1:
                    results = _group_affil_results(
                        matches_affiliation(query, self._records)
                    )
                else:
                    results = matches(query, self._records)
            except Exception as exc:
                QMessageBox.critical(
                    self, "검색 오류", f"검색 중 오류 발생:\n{exc}"
                )
                return
        finally:
            QApplication.restoreOverrideCursor()

        self._current_results = results
        self._current_query = query
        self._render_results(results)

        mode_label = "소속" if mode == 1 else "이름"
        if results:
            self.count_label.setText(f"'{query}' {mode_label} 검색 결과: {len(results)}건")
            self._set_export_enabled(True)
        else:
            self.count_label.setText(f"'{query}' {mode_label} 검색 결과: 0건")
            self._set_export_enabled(False)

    def _render_results(self, results: list[dict]) -> None:
        self._clear_results()
        for rec in results:
            card = SessionCard(rec)
            # insert before the trailing stretch
            self.results_layout.insertWidget(
                self.results_layout.count() - 1, card
            )
        self.scroll.verticalScrollBar().setValue(0)

    def _clear_results(self) -> None:
        while self.results_layout.count() > 1:  # keep trailing stretch
            item = self.results_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _set_export_enabled(self, enabled: bool) -> None:
        for btn in (self.txt_btn, self.xlsx_btn, self.ics_btn):
            btn.setEnabled(enabled)

    # -- export --------------------------------------------------------------

    def _default_export_name(self, ext: str) -> str:
        event = self._event_meta.get("event_name", "schedule") or "schedule"
        base = _sanitize_filename(
            f"{event}_{self._current_query}_schedule"
        )
        return f"{base}.{ext}"

    def _ask_save_path(self, ext: str, label: str) -> Optional[Path]:
        default = self._default_export_name(ext)
        start_dir = str(self._pdf_path.parent) if self._pdf_path else ""
        start_path = (
            str(Path(start_dir) / default) if start_dir else default
        )

        path_str, _ = QFileDialog.getSaveFileName(
            self,
            f"{label} 저장",
            start_path,
            f"{label} files (*.{ext})",
        )
        if not path_str:
            return None
        path = Path(path_str)
        if path.suffix.lower() != f".{ext}":
            path = path.with_suffix(f".{ext}")
        return path

    def _on_export_txt(self) -> None:
        path = self._ask_save_path("txt", "TXT")
        if not path:
            return
        try:
            export_text(
                self._current_results,
                self._event_meta.get("event_timezone", ""),
                path,
                event_name=self._event_meta.get("event_name", ""),
                event_location=self._event_meta.get("event_location", ""),
            )
        except Exception as exc:
            QMessageBox.critical(self, "TXT 저장 실패", str(exc))
            return
        QMessageBox.information(
            self, "저장 완료", f"TXT 파일을 저장했습니다:\n{path}"
        )

    def _on_export_xlsx(self) -> None:
        path = self._ask_save_path("xlsx", "XLSX")
        if not path:
            return
        try:
            export_xlsx(
                self._current_results,
                self._event_meta.get("event_timezone", ""),
                path,
                event_name=self._event_meta.get("event_name", ""),
                event_location=self._event_meta.get("event_location", ""),
                query=self._current_query,
            )
        except Exception as exc:
            QMessageBox.critical(self, "XLSX 저장 실패", str(exc))
            return
        QMessageBox.information(
            self, "저장 완료", f"XLSX 파일을 저장했습니다:\n{path}"
        )

    def _on_export_ics(self) -> None:
        path = self._ask_save_path("ics", "ICS")
        if not path:
            return
        try:
            export_ics(
                self._current_results,
                self._event_meta.get("event_timezone", ""),
                path,
                event_name=self._event_meta.get("event_name", ""),
            )
        except Exception as exc:
            QMessageBox.critical(self, "ICS 저장 실패", str(exc))
            return
        QMessageBox.information(
            self, "저장 완료", f"ICS 파일을 저장했습니다:\n{path}"
        )
