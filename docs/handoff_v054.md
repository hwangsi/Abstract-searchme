# Abstract Searcher — Stage Handoff (v0.5.4)

**Date**: 2026-05-19  
**Branch**: `desktop-app`  
**Last commit**: `83578fa` — docs: README v0.5.4

---

## 현재 상태 요약

데스크톱 앱(PySide6) + CLI 모두 동작 중.  
KCR / ICR / GBCC 3개 어댑터, 17개 ground truth 테스트 통과.  
`dist/AbstractSearcher.exe` (69MB onefile) 빌드 완료.

---

## 아키텍처

```
abstract-searcher/
├── core/
│   ├── adapters/
│   │   ├── __init__.py       load_pdf(path) → (records, event_meta)
│   │   ├── affil_refs.py     superscript ref 파싱 (¹²³ → per-author affil)
│   │   ├── post.py           normalize_records() — dedup + I1-I5 invariant
│   │   ├── kcr.py            KCR 2025 파서
│   │   ├── icr.py            ICR 2026 파서
│   │   ├── gbcc.py           GBCC 2026 파서
│   │   └── generic.py        fallback
│   ├── exporters/
│   │   ├── ics_exporter.py   RFC 5545 VTIMEZONE
│   │   ├── text_exporter.py
│   │   ├── xlsx_exporter.py
│   │   └── html_exporter.py  standalone HTML viewer
│   └── search/
│       └── matcher.py        matches() + matches_affiliation()
├── desktop/
│   ├── main.py               엔트리포인트 (오류 → temp log + QMessageBox)
│   └── windows/
│       ├── upload_window.py  Window 1: PDF 드래그앤드롭 + 파싱
│       └── search_window.py  Window 2: 이름/소속 검색 + 결과카드 + export
├── cli/
│   └── main.py               CLI
├── tests/
│   └── test_ground_truth.py  17개 회귀 테스트
└── build/
    └── abstract_searcher.spec  PyInstaller onefile/windowed
```

---

## 레코드 스키마

`load_pdf()` 가 반환하는 각 레코드 필드:

```python
{
    "page": int,
    "date": str,            # "Sep. 26 (Fri)"
    "time": str,            # "14:00-14:20"
    "room": str,
    "session_code": str,
    "session_title": str,
    "role": str,            # "chair" | "speaker" | "discussant" | "panelist"
    "is_primary_author": bool,
    "person": str,          # trailing digit 제거됨 (normalize_records)
    "affiliation": str,
    "talk_title": str,
    "authors_all": list[str],  # 해당 발표의 전체 저자 목록
}
```

**Invariants (normalize_records 보장)**  
- I2: 같은 talk의 모든 레코드는 동일한 `authors_all`  
- I3: `authors_all` 비어있지 않음  
- I4: 각 talk에 `is_primary_author=True` 레코드 정확히 1개  
- I5: chair/discussant/panelist의 `authors_all == [person]`

---

## 검색 동작

### matches(query, records)
- rapidfuzz partial_ratio 기반 퍼지 매칭 (threshold 기본 80)
- 토큰을 AND 조건으로 처리: "Sung Hwang" → "Sung" AND "Hwang" 모두 포함
- `person` 필드 검색
- `_score` 키 추가해 반환

### matches_affiliation(query, records)
- 쿼리를 토큰으로 분리 → 모든 토큰이 `affiliation`에 포함된 레코드
- (person, date, time, room, talk_title, role) 기준 dedup
- 동일 발표가 PDF 두 페이지에 걸치는 경우 하나로 합산

---

## KCR 어댑터 주요 포인트 (kcr.py)

### Talk code 포맷 (모두 인식)
```
SS 15-IR-08          ← 구형
IDP 04 NR-01         ← 신형
JS 09 HN-01
KSR 03 KSR-01
SF 10 AB-01
SS 05- CV-01         ← 공백+하이픈
SE 10 NR(HN)-06      ← 괄호형
SS 26-03
WORD-01
```

### 파싱 흐름
```
날짜줄 감지 → 세션 컨텍스트 갱신
↓
Talk code 줄 → in_talk_title = True
↓
제목 줄 누적 (talk_title_parts)
↓
저자 줄 감지 (is_likely_author 휴리스틱)
  OR 소속+국가 줄 감지 (Path B)
↓
pending_talk 버퍼에 저장
↓
소속 줄 누적 (pending_affil_parts)
↓
flush_pending() → affil_dict 파싱 + per-author affil 해석 → records emit
```

### is_likely_author 조건 (False positive 방지)
```python
is_likely_author = (
    talk_title_parts and
    not line.endswith(":") and
    ":" not in line and          # ← subtitle 연속 방지
    not re.search(r"\d", line[:20]) and
    (
        "," in line or
        (not re.search(r"[.!?]$", line) and
         len(line.split()) <= 5 and
         re.match(r"[A-Z][a-z]", line))
    )
)
# fallback 단일 이름: len(name.split()) >= 2 필수
```

---

## 빌드 방법

```powershell
# 의존성 설치
.\.venv\Scripts\python.exe -m pip install pyinstaller

# 빌드 (약 2분)
.\.venv\Scripts\python.exe -m PyInstaller build\abstract_searcher.spec --noconfirm

# 결과물: dist\AbstractSearcher.exe (69MB)
```

### build/abstract_searcher.spec 핵심 설정
- `onefile=True`, `windowed=True` (콘솔창 없음)
- `collect_all('pymupdf')`, `collect_all('ics')`
- hiddenimports: `core.*`, `rapidfuzz`, `openpyxl`, `PySide6.*`
- 에러 로그: `%TEMP%\abstractsearcher.log`

---

## 테스트 실행

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -v
# 17 passed
```

### 주요 테스트 목록
| 테스트 | 검증 내용 |
|---|---|
| `test_icr_sung_hwang_2_hits` | ICR 이름 검색 |
| `test_kcr_jin_mo_goo_3_hits` | KCR chair 검색 |
| `test_gbcc_sun_young_min_3_hits` | GBCC 이름 검색 |
| `test_kcr_speaker_affiliation_filled` | speaker 소속 fill rate > 50% |
| `test_kcr_affiliation_seoul_national_includes_speakers` | SNU 소속 검색에 speaker 포함 |
| `test_kcr_coauthor_records_present` | 공저자 레코드 존재 |
| `test_kcr_p55_magnus_hcc_superscript_snuh_authors` | 위첨자 per-author 소속 매핑 |
| `test_kcr_affiliation_snuh_total_count_not_regressed` | SNUH >= 49 hits |
| `test_kcr_affiliation_bundang_lower_bound` | Bundang >= 20 hits |
| `test_invariants_kcr/icr/gbcc` | I2-I5 전체 어댑터 |
| `test_kcr_no_trailing_digit_in_person` | person 필드 끝자리 숫자 없음 |

---

## 알려진 이슈 / 미해결 사항

1. **p.116 Bundang GT miss**: "AI-Based Pulmonary Embolism Detection" (SE 03 CV-01)이 p.100과 p.116 두 페이지에 걸쳐 인쇄됨. dedup 로직에 의해 p.100 하나로 합산 → 정상 동작, GT miss 아님.

2. **CLI affiliation 플래그**: `--affiliation` 옵션이 README에 명시돼 있으나 `cli/main.py`에 아직 구현 안 됨. 현재는 `--name` 만 동작.

3. **ICR/GBCC co-author affil 정확도**: superscript 기반 per-author 소속 매핑이 KCR에만 충분히 검증됨. ICR/GBCC는 layout이 달라 별도 검증 필요.

4. **main branch 병합 미완**: 모든 작업이 `desktop-app` 브랜치. `main`에 PR 미생성.

---

## 다음 단계 후보

| 우선순위 | 작업 |
|---|---|
| 높음 | `desktop-app` → `main` PR 생성 및 병합 |
| 높음 | CLI `--affiliation` 옵션 구현 |
| 중간 | 새 PDF 추가 지원 (다른 컨퍼런스) |
| 중간 | GBCC/ICR co-author 소속 매핑 검증 |
| 낮음 | 결과 카드 UI 개선 (페이지 표시, 소속 표시) |
| 낮음 | `dist/AbstractSearcher.exe` GitHub Release 업로드 |

---

## 새 세션 시작 체크리스트

```
□ git checkout desktop-app
□ git pull
□ .venv\Scripts\python.exe -m pytest tests/ -v   # 17 passed 확인
□ data/pdfs/ 에 PDF 파일 존재 확인
□ 작업 시작
```
