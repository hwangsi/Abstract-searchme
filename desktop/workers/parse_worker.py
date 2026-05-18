"""QThread PDF 파싱 워커 — UI freeze 방지."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal


class ParseWorker(QThread):
    """PDF를 백그라운드 스레드에서 파싱한다."""

    parsed = Signal(object, object)   # (records: list, event_meta: dict)
    error  = Signal(str)              # 에러 메시지 (한국어)

    def __init__(self, pdf_path: Path, parent=None) -> None:
        super().__init__(parent)
        self._pdf_path = pdf_path

    def run(self) -> None:
        try:
            from core.adapters import load_pdf

            records, event_meta = load_pdf(self._pdf_path)

            if not records:
                self.error.emit(
                    "이 학회 형식을 인식하지 못했습니다.\n"
                    "세션 정보를 찾을 수 없습니다."
                )
                return

            self.parsed.emit(records, event_meta)

        except FileNotFoundError:
            self.error.emit(
                "파일을 열 수 없습니다.\n파일이 존재하는지 확인해주세요."
            )
        except PermissionError:
            self.error.emit(
                "파일을 열 수 없습니다.\n파일 접근 권한을 확인해주세요."
            )
        except Exception as exc:
            logging.exception("PDF 파싱 오류")
            msg = str(exc)
            if "password" in msg.lower() or "encrypt" in msg.lower():
                self.error.emit("암호로 보호된 PDF는 열 수 없습니다.")
            else:
                self.error.emit(
                    f"이 학회 형식을 인식하지 못했습니다.\n\n"
                    f"{type(exc).__name__}: {msg[:200]}"
                )
