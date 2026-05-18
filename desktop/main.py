"""데스크탑 GUI 진입점 (PySide6, Windows)."""
from __future__ import annotations

import io
import sys


def main() -> None:
    # Windows: stdout/stderr UTF-8 (한글 출력 깨짐 방지)
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    from PySide6.QtWidgets import QApplication

    from desktop.windows.search_window import SearchWindow
    from desktop.windows.upload_window import UploadWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Abstract Searcher")

    upload_win = UploadWindow()
    search_win = SearchWindow()

    def on_ready(records, event_meta, pdf_path):
        search_win.load(records, event_meta, pdf_path)
        search_win.show()
        upload_win.hide()

    def go_back():
        upload_win.show()
        search_win.hide()

    upload_win.ready.connect(on_ready)
    search_win.back_requested.connect(go_back)

    upload_win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
