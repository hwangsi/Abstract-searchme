# Handoff: abstract-searcher Stage 3d (complete)

## 이번 세션에서 한 일

| 파일 | 변경 내용 |
|---|---|
| `exporters/text_exporter.py` | **신규.** 이메일용 plain text export (정렬, prefix, 80자 wrap) |
| `exporters/xlsx_exporter.py` | **신규.** openpyxl xlsx export (Arial, bold header, freeze pane) |
| `search/cli.py` | `--text <path>`, `--xlsx <path>` 옵션 추가 |
| `requirements.txt` | `openpyxl>=3.0` 추가 |

### Stage 3c에서 한 일 (이전 세션)

| 파일 | 변경 내용 |
|---|---|
| `exporters/ics_exporter.py` | **신규.** RFC 5545 준수 ICS 생성 (VTIMEZONE + TZID) |
| `search/cli.py` | `--ics <path>` 옵션 추가 (ics_exporter 사용) |
| `exporters/html_exporter.py` | JS ICS 로직 업데이트 (VTIMEZONE + buildSummary) |
| `data/sessions/icr_viewer.html` | 재빌드 (새 ICS 포맷 반영) |
| `data/sessions/kcr_viewer.html` | 재빌드 (새 ICS 포맷 반영) |

---

## ics_exporter.py 개요

ics 0.7.3은 모든 경로에서 VTIMEZONE을 생성하지 않으므로 RFC 5545 텍스트를 직접 생성합니다.
`arrow`는 ics의 의존성으로 설치되므로 datetime 연산에 사용합니다.

```python
from exporters.ics_exporter import export_ics

export_ics(
    sessions=hits,
    event_timezone="America/Bogota",
    output_path="out.ics",
    event_name="ICR 2026",
)
```

### CLI

```bash
python -m search.cli \
  --pdf "data/pdfs/EN-ICR 2026 f. prog_110526.pdf" \
  --name "Sung Hwang" --threshold 80 \
  --ics results/sung_hwang.ics
```

> `--ics` (신규, VTIMEZONE 포함) vs `--export-ics` (구버전, UTC만): `--ics` 사용 권장.

---

## ICS 출력 형식

### ICR (America/Bogota, UTC-5) 예시

```
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//abstract-searcher//EN
CALSCALE:GREGORIAN
BEGIN:VTIMEZONE
TZID:America/Bogota
BEGIN:STANDARD
DTSTART:19700101T000000
TZOFFSETFROM:-0500
TZOFFSETTO:-0500
TZNAME:COT
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:...@abstract-searcher
SUMMARY:★ AI and radiology: Turning crisis into opportunity for residency
  education
DTSTART;TZID=America/Bogota:20260514T140000
DTEND;TZID=America/Bogota:20260514T142000
LOCATION:Room Barahona 4
DESCRIPTION:Sung Hwang\nRole: speaker\nEvent: ICR 2026
END:VEVENT
```

### SUMMARY 포맷

| 조건 | 형식 | 예시 |
|---|---|---|
| `is_primary_author=True` + `talk_title` | `★ {talk_title}` | `★ AI and radiology: ...` |
| chair / discussant | `[{Role}] {session_code}: {session_title}` | `[Chair] SS 12: Deep-Learning...` |

### 폰 import 테스트

한국 폰 (Asia/Seoul = UTC+9)에서 ICR Bogotá 세션(UTC-5) import 시:
- `DTSTART;TZID=America/Bogota:20260514T140000` → Bogotá 14:00 (UTC-5) = UTC 19:00 = **KST 05월 15일 04:00** (+14h) ✓

---

## 검증 결과

| 쿼리 | PDF | 기대 | 결과 |
|---|---|---|---|
| "Sung Hwang" | ICR 2026 | 2 VEVENT, SUMMARY "★ ..." | **통과** |
| "Jin Mo Goo" | KCR 2025 | 3 VEVENT, SUMMARY "[Chair] ..." | **통과** |
| VTIMEZONE | 양쪽 | VTIMEZONE 블록 포함 | **통과** |
| JS 문법 | icr_viewer.html | Node.js v24 OK | **통과** |
| 폰 테스트 | ICR TZID | UTC-5 → KST +14h | **✓ (수식 확인)** |

---

## 현재 스키마 요약

### Record 필드
```json
{
  "page": 48,
  "date": "Sep. 26 (Fri)",
  "time": "12:20-13:20",
  "room": "Grand Ballroom 101-102",
  "session_code": "LS 09",
  "session_title": "Optimizing CT Contrast Dosing with Innovative Technology",
  "role": "chair",
  "is_primary_author": false,
  "person": "Jin Mo Goo",
  "affiliation": "Seoul National University Hospital, Korea",
  "talk_title": ""
}
```

### sessions.json 최상위
```json
{
  "event_name": "KCR 2025",
  "event_location": "Seoul, Korea",
  "event_timezone": "Asia/Seoul",
  "sessions": [ ... ]
}
```

---

## CLI 전체 옵션 정리

```bash
python -m search.cli \
  --pdf <path>          # PDF 경로 (필수)
  --name "<query>"      # 검색어 (필수)
  --threshold 80        # 유사도 임계값 (기본 80)
  --save                # sessions.json 저장
  --json                # JSON으로 출력
  --export-html <path>  # 검색 결과 HTML 표
  --export-ics <path>   # 검색 결과 ICS (구버전, UTC)
  --ics <path>          # 검색 결과 ICS (신버전, VTIMEZONE) ← 권장

python -m exporters.html_exporter <sessions.json> [<output.html>]
  # sessions.json 전체 → standalone viewer.html (실시간 검색 UI)
```

---

## 알려진 이슈 / 주의사항

### Python 경로
```
/c/Users/hwang/AppData/Local/Python/bin/python.exe
```

### VTIMEZONE 범위
`exporters/ics_exporter.py` 의 `_VTIMEZONE` dict에 없는 시간대는 UTC 폴백.  
새 학회 추가 시 해당 dict에 VTIMEZONE 블록 추가 필요.

### ics 0.7.3 한계
표준 ics API로는 VTIMEZONE 생성 불가 → `ics_exporter.py`가 직접 생성.  
`--export-ics` (구버전)는 UTC만 사용; `--ics` (신버전)는 VTIMEZONE 포함.

### KCR Speaker 검출
KCR 과학 세션(SS) 발표자 추출은 휴리스틱 기반; chair 검색이 주 use-case.

### ICR bio section
x≈296–298 bio 섹션 `_col(x)` 임계값으로 배제. 레이아웃 변경 시 재조정.

---

---

## text_exporter.py 개요

```python
from exporters.text_exporter import export_text

export_text(
    sessions=hits,
    event_timezone="America/Bogota",
    output_path="out.txt",
    event_name="ICR 2026",
    event_location="Cartagena, Colombia",
)
```

### 출력 형식

```
ICR 2026 — Cartagena, Colombia (America/Bogota)
===============================================

* Thursday, May 14, 2026  14:00–14:20  Room Barahona 4
  AI and radiology: Turning crisis into opportunity for residency education

[Chair] Thursday, September 25, 2025  16:30–17:50  Grand Ballroom 101
  [SS 12 - Deep-Learning Application in Chest Radiograph]
```

---

## xlsx_exporter.py 개요

```python
from exporters.xlsx_exporter import export_xlsx

export_xlsx(
    sessions=hits,
    event_timezone="Asia/Seoul",
    output_path="out.xlsx",
    event_name="KCR 2025",
    event_location="Seoul, Korea",
    query="Jin Mo Goo",
)
```

### 시트 구조

- 행 1-3 (또는 1-4): Event / Location / Timezone / Query (메타)
- 다음 행: 헤더 (bold Arial, 파란 배경, freeze pane)
- 데이터 행: Date (YYYY-MM-DD), Day, Start (HH:MM), End, Room, Role, Primary Author (Y/N), Session Code, Title, Event

---

## CLI 전체 옵션 정리

```bash
python -m search.cli \
  --pdf <path>          # PDF 경로 (필수)
  --name "<query>"      # 검색어 (필수)
  --threshold 80        # 유사도 임계값 (기본 80)
  --save                # sessions.json 저장
  --json                # JSON으로 출력
  --export-html <path>  # 검색 결과 HTML 표
  --export-ics <path>   # 검색 결과 ICS (구버전, UTC)
  --ics <path>          # 검색 결과 ICS (신버전, VTIMEZONE) ← 권장
  --text <path>         # 검색 결과 plain text (이메일용)
  --xlsx <path>         # 검색 결과 xlsx 스프레드시트

python -m exporters.html_exporter <sessions.json> [<output.html>]
  # sessions.json 전체 → standalone viewer.html (실시간 검색 UI)
```

---

## 다음 Stage 후보

- Stage 4: GUI (Streamlit/Gradio) 래퍼
- 새 학회 adapter 추가
- Abstract 텍스트 파싱
