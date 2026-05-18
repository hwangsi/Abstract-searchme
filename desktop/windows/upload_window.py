"""Window 1: PDF 파일 열기, 드래그앤드롭, QThread 파싱."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop.workers.parse_worker import ParseWorker


class _DropZone(QLabel):
    """PDF 드래그앤드롭 수신 영역."""

    dropped = Signal(object)   # Path

    _IDLE = (
        "QLabel {"
        "  border: 2px dashed #b0b8c1;"
        "  border-radius: 14px;"
        "  background: #f5f6f8;"
        "  color: #888;"
        "  font-size: 15px;"
        "  line-height: 1.6;"
        "  padding: 40px;"
        "}"
    )
    _HOVER = (
        "QLabel {"
        "  border: 2px dashed #4a90e2;"
        "  border-radius: 14px;"
        "  background: #e8f0fe;"
        "  color: #4a90e2;"
        "  font-size: 15px;"
        "  line-height: 1.6;"
        "  padding: 40px;"
        "}"
    )
    _BUSY = (
        "QLabel {"
        "  border: 2px dashed #cccccc;"
        "  border-radius: 14px;"
        "  background: #f0f0f0;"
        "  color: #bbb;"
        "  font-size: 15px;"
        "  line-height: 1.6;"
        "  padding: 40px;"
        "}"
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("PDF를 여기에 드래그하거나\n아래 버튼을 클릭하세요")
        self.setStyleSheet(self._IDLE)
        self.setMinimumHeight(200)

    def set_busy(self, busy: bool) -> None:
        self.setEnabled(not busy)
        self.setStyleSheet(self._BUSY if busy else self._IDLE)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    self.setStyleSheet(self._HOVER)
                    return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: ANN001
        self.setStyleSheet(self._IDLE)

    def dropEvent(self, event: QDropEvent) -> None:
        self.setStyleSheet(self._IDLE)
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() == ".pdf":
                event.acceptProposedAction()
                self.dropped.emit(path)
                return
        event.ignore()


class UploadWindow(QWidget):
    """Window 1: PDF 파일 선택 및 파싱."""

    ready = Signal(object, object, object)  # (records: list, event_meta: dict, pdf_path: Path)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Abstract Searcher")
        self.setMinimumSize(500, 420)
        self._worker: ParseWorker | None = None
        self._setup_ui()

    # ── UI 구성 ───────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 36, 40, 36)
        layout.setSpacing(16)

        title = QLabel("학회 프로그램 검색")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 24px; font-weight: bold; color: #1a1a2e; margin-bottom: 2px;"
        )
        layout.addWidget(title)

        subtitle = QLabel("학회 PDF를 불러오면 발표자·좌장을 이름 또는 소속으로 검색할 수 있습니다.")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("font-size: 13px; color: #888;")
        layout.addWidget(subtitle)

        self._drop_zone = _DropZone()
        self._drop_zone.dropped.connect(self._start_parse)
        layout.addWidget(self._drop_zone)

        self._btn = QPushButton("PDF 파일 선택")
        self._btn.setMinimumHeight(44)
        self._btn.setStyleSheet(
            "QPushButton {"
            "  background: #4a90e2; color: white;"
            "  border: none; border-radius: 7px;"
            "  font-size: 14px; font-weight: bold;"
            "}"
            "QPushButton:hover { background: #357abd; }"
            "QPushButton:disabled { background: #c0cfe8; color: #e8eef8; }"
        )
        self._btn.clicked.connect(self._open_dialog)
        layout.addWidget(self._btn)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)   # indeterminate marquee
        self._progress.setVisible(False)
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        layout.addWidget(self._progress)

        self._status = QLabel()
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet("font-size: 13px; color: #555;")
        self._status.setVisible(False)
        layout.addWidget(self._status)

    # ── 이벤트 핸들러 ─────────────────────────────────────────────────────────

    def _open_dialog(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "PDF 파일 열기",
            str(Path.home()),
            "PDF 파일 (*.pdf);;모든 파일 (*)",
        )
        if path_str:
            self._start_parse(Path(path_str))

    def _start_parse(self, pdf_path: Path) -> None:
        self._set_busy(True, pdf_path.name)

        # 이전 워커가 아직 실행 중이면 완료 대기
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait()

        self._worker = ParseWorker(pdf_path, parent=self)
        self._worker.parsed.connect(
            lambda records, meta: self._on_parsed(records, meta, pdf_path)
        )
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_parsed(self, records: list, event_meta: dict, pdf_path: Path) -> None:
        self._set_busy(False)
        self.ready.emit(records, event_meta, pdf_path)

    def _on_error(self, message: str) -> None:
        self._set_busy(False)
        QMessageBox.critical(self, "오류", message)

    # ── 상태 제어 ─────────────────────────────────────────────────────────────

    def _set_busy(self, busy: bool, filename: str = "") -> None:
        self._btn.setEnabled(not busy)
        self._drop_zone.set_busy(busy)
        self._progress.setVisible(busy)
        self._status.setVisible(busy)
        if busy:
            self._status.setText(f"분석 중입니다...   {filename}")
