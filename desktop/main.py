"""데스크탑 GUI 진입점 (PySide6, Windows)."""
from __future__ import annotations

import io
import os
import sys
import tempfile
import traceback


def _log_path() -> str:
    return os.path.join(tempfile.gettempdir(), "abstractsearcher.log")


def _write_log(msg: str) -> None:
    try:
        with open(_log_path(), "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def main() -> None:
    try:
        # Windows: stdout/stderr UTF-8 (한글 출력 깨짐 방지)
        # In windowed exe mode sys.stdout/stderr may be None — skip wrapping if so
        if sys.stdout is not None and hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if sys.stderr is not None and hasattr(sys.stderr, "buffer"):
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

    except Exception:
        tb = traceback.format_exc()
        _write_log("EXCEPTION:\n" + tb)
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            _app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, "AbstractSearcher Error", tb)
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
