# Handoff: abstract-searcher Stage 5c (완료)

## 브랜치 / 커밋

```
브랜치: desktop-app
최신 커밋: 641364c  Stage 5c: Window 2 검색 + 결과 카드 + export 3종
이전 커밋: 75c40b7  Stage 5a+5b: 모노레포 리팩토링 + PySide6 Window 1 구현
```

---

## 이번 세션에서 한 일 (Stage 5a → 5c)

### 5a: 폴더 구조 리팩토링
| 전 | 후 |
|---|---|
| `adapters/` | `core/adapters/` |
| `parsers/` | `core/parsers/` |
| `search/matcher.py` | `core/search/matcher.py` |
| `exporters/` | `core/exporters/` |
| `main.py` (루트) | `core/main.py` |
| `search/cli.py` | `cli/main.py` |

CLI 진입점: `python -m search.cli` → **`python -m cli.main`**

### 5b: Window 1 (파일 열기 + QThread 파싱)
- `desktop/workers/parse_worker.py` — `ParseWorker(QThread)`
- `desktop/windows/upload_window.py` — `UploadWindow` + `_DropZone`
- `desktop/main.py` — 앱 진입점, 창 전환 관리

### 5c: Window 2 (검색 + 결과 카드 + export 3종)
- `desktop/windows/search_window.py` — `SearchWindow` + `SessionCard` (사용자 제공 코드)

---

## 현재 폴더 구조

```
abstract-searcher/
  core/
    adapters/   icr.py  kcr.py  generic.py
    exporters/  ics_exporter.py  text_exporter.py  xlsx_exporter.py  html_exporter.py  ics.py  html.py
    search/     matcher.py
    parsers/    pdf_parser.py
    main.py     (_detect_adapter, search_pdf, _wrap_generic)
  cli/
    main.py     (python -m cli.main)
  desktop/
    main.py     (python -m desktop.main  ← GUI 진입점)
    windows/
      upload_window.py
      search_window.py
    workers/
      parse_worker.py
    resources/  (.gitkeep — icon.ico 미구현, 5e에서 추가)
  data/
    pdfs/       EN-ICR 2026 f. prog_110526.pdf  /  KCR2025_Program_Book.pdf
    sessions/   (파싱 결과 JSON 캐시)
  results/      (export 테스트 파일들)
  pyproject.toml
  build_win.bat
  requirements.txt
```

---

## 핵심 인터페이스 (5d/5e 작업 시 참고)

### UploadWindow → SearchWindow 연결

```python
# desktop/main.py
upload_win.ready.connect(on_ready)          # Signal(object, object, object)
search_win.back_requested.connect(go_back)  # Signal()

def on_ready(records, event_meta, pdf_path):
    search_win.load(records, event_meta, pdf_path)
    search_win.show()
    upload_win.hide()
```

`records` : `list[dict]` — adapter.parse() 반환값 전체 (필터링 없음)  
`event_meta` : `dict` — `{"event_name", "event_location", "event_timezone"}`  
`pdf_path` : `pathlib.Path`

### 검색 함수

```python
# core/search/matcher.py
def matches(query: str, records: list[dict], threshold: float = 80.0) -> list[dict]:
```
- `role` 필드: 문자열 `"speaker"` / `"chair"` / `"discussant"`
- 반환: 원본 dict + `_score: float` 추가

### Record 필드 스키마

```python
{
    "page": int,
    "date": str,            # "Sep. 26 (Fri)" / "Thursday, May 14th"
    "time": str,            # "14:00-14:20"
    "room": str,
    "session_code": str,
    "session_title": str,
    "role": str,            # "chair" | "speaker" | "discussant"
    "is_primary_author": bool,
    "person": str,
    "affiliation": str,
    "talk_title": str,
    "_score": float,        # matches() 결과에만 존재
}
```

### Exporter 시그니처

```python
from core.exporters.text_exporter import export_text
from core.exporters.xlsx_exporter import export_xlsx
from core.exporters.ics_exporter  import export_ics

export_text(sessions, event_timezone, output_path, event_name="", event_location="")
export_xlsx(sessions, event_timezone, output_path, event_name="", event_location="", query="")
export_ics (sessions, event_timezone, output_path, event_name="")
# 모두 None 반환, output_path는 str | Path
```

---

## 검증 상태

| 항목 | 상태 |
|---|---|
| `python -m cli.main` ICR "Sung Hwang" 2건 | ✅ |
| `python -m cli.main` KCR "Jin Mo Goo" 3건 chair | ✅ |
| TXT/XLSX/ICS export (ICR + KCR) | ✅ |
| SearchWindow import / Signal / load() | ✅ |
| SessionCard 필드 누락 없음 | ✅ |
| `python -m desktop.main` GUI 실행 | ⬜ 수동 테스트 필요 |

---

## 남은 작업

### 5d: 소속 검색 모드 추가
`search_window.py`에 **소속(affiliation) 검색** 기능 추가.

스펙:
- 검색 모드 라디오: `⦿ 이름으로  ○ 소속으로`
- 소속 토큰 부분 매칭 예시:
  - "SNUBH" / "Seoul National" / "Bundang" → "Seoul National University Bundang Hospital" 매칭
- `core/search/matcher.py`에 `matches_affiliation(query, records)` 함수 추가 또는 `matches()` 확장
- 현재 `matches()`는 `person` 필드만 검색 → 소속 모드는 `affiliation` 필드 토큰 매칭

구현 위치:
- `core/search/matcher.py` — 소속 검색 로직 추가
- `desktop/windows/search_window.py` — 라디오 버튼 UI + 모드 분기

### 5e: PyInstaller 빌드
```bat
# build_win.bat (이미 존재)
pyinstaller --onefile --windowed --name AbstractSearcher --icon desktop\resources\icon.ico desktop\main.py
```

주의사항:
- `desktop/resources/icon.ico` 아직 없음 (placeholder만 있음) → 빌드 전 실제 .ico 파일 필요
- PyInstaller hidden imports 확인 필요: `fitz`, `rapidfuzz`, `openpyxl`, `ics`, `PySide6`
- `--add-data` 옵션으로 core/ 패키지 포함 여부 확인
- 빌드 후 `dist/AbstractSearcher.exe`로 ground truth 재검증

---

## Python 경로 (Windows Bash 도구에서)

```
/c/Users/hwang/AppData/Local/Python/bin/python.exe
```
bare `python` 명령은 Windows Store stub 충돌 → 항상 전체 경로 사용.

---

## 알려진 이슈 / 주의사항

- `desktop/resources/icon.ico` 없음 — `build_win.bat`에 분기 처리 있음 (없으면 `--icon` 생략)
- `search_window.py`의 `QSizePolicy.Fixed` 는 PySide6에서 `QSizePolicy.Policy.Fixed`가 권장됨 — 현재 동작은 하지만 deprecation 경고 가능성 있음
- 한글 파일명 PDF: `fitz.open(str(Path(...)))` 으로 처리, Windows UTF-8 경로 정상 동작 확인 필요
- `Inno Setup` 설치 파일, `GitHub Actions` 자동 빌드는 **v0.2 별도 단계**
