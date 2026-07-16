# Abstract Searcher — 온라인 서비스 설계서

작성: 2026-07-16 · 상태: 설계 확정 (구현 전)

## 0. 확정된 결정

| 항목 | 결정 | 근거 |
|---|---|---|
| 플랫폼 | **Vercel** (Next.js 프론트 + Python 서버리스) | `core/` 파서(PyMuPDF)를 한 줄도 안 고치고 재사용. Cloudflare Workers는 C 확장 불가 |
| 푸시 채널 | **Web Push (PWA)** + 기존 `.ics` 이중화 | 앱스토어 없이 무료. iPhone은 홈 화면 추가 필수 (§7) |
| 사용 범위 | **본인 + 동료 공유** (로그인 없음) | 링크 접근 + PDF 해시 공유 캐시. 계정/OAuth 없이 시작 |

## 1. 아키텍처

```
[브라우저 PWA (Next.js)]
   │ ① PDF 클라이언트 직접 업로드 (@vercel/blob client upload — 4.5MB 함수 제한 우회)
   ▼
[Vercel Blob]  키 = sha256(file) → 같은 학회 PDF는 전역 1회만 저장/파싱
   │ ② onUploadCompleted → POST /api/parse
   ▼
[api/parse.py — Python 서버리스]  기존 core.main.search_pdf 경로 재사용 (파싱만 분리)
   │ ③ records[] → Postgres 저장, conferences.status = 'ready'
   ▼
[Neon Postgres]
   │ ④ GET /api/search — rapidfuzz 매칭 (records는 DB에서 로드, PDF 재파싱 없음)
   ▼
[결과 화면] ── "알림 받기" ──▶ POST /api/subscribe
   │ ⑤ 세션별 QStash 예약 발행 (시작 −60분, −10분; 오프셋 사용자 선택)
   ▼
[QStash] ──(예약 시각)──▶ POST /api/push (서명 검증) ──web-push/VAPID──▶ 📱
```

## 2. 리포 구조 (M1 스캐폴딩 반영 — 2026-07-16 갱신)

레포 루트가 곧 Vercel 프로젝트 루트 (Vercel 공식 Next.js+Python 하이브리드 패턴).
`web/` 하위 분리안은 폐기 — Root Directory를 설정하면 `core/`가 배포 번들 밖으로
빠져 Python 함수가 파서를 import할 수 없기 때문.

```
abstract-searcher/
├── core/                  # 기존 그대로 — 수정 없음 (데스크톱/CLI와 공유)
├── src/app/               # Next.js App Router (PWA는 M2에서 manifest+sw 추가)
│   ├── page.tsx           #   홈: 업로드 + 학회 목록
│   ├── conf/[id]/page.tsx #   검색 + 결과 + .ics
│   └── api/upload/route.ts#   Blob 클라이언트 업로드 토큰 (Node 런타임)
├── api/                   # Vercel Python Functions (파일당 1함수, 개별 번들)
│   ├── _lib/              #   공유 코드 (db.py, searchlib.py — 함수로 노출 안 됨)
│   ├── parse.py           #   Blob → core 파서 → DB (M1)
│   ├── search.py          #   이름/소속 fuzzy 검색 (M1)
│   ├── ics.py             #   기존 exporters/ics_exporter 재사용 (M1)
│   ├── conferences.py     #   학회 목록 (M1)
│   ├── subscribe.py       #   푸시 구독 + QStash 예약 (M2)
│   ├── push.py            #   QStash 웹훅 수신 → web-push 발송 (M2)
│   └── requirements.txt   #   웹 함수 의존성 (루트 requirements.txt는 데스크톱용, .vercelignore로 제외)
├── db/schema.sql          # Neon 스키마 (M2 테이블 포함)
├── scripts/init_webdb.py  # 스키마 적용 스크립트
└── vercel.json            # 함수별 maxDuration + includeFiles(core/**, api/_lib/**)
```

개발/배포 절차는 docs/WEB_DEV.md 참조.

## 3. DB 스키마 (Neon Postgres)

```sql
CREATE TABLE conferences (
  id          bigserial PRIMARY KEY,
  sha256      char(64) UNIQUE NOT NULL,       -- 공유 캐시 키
  title       text NOT NULL,                  -- "KCR 2025"
  tz          text NOT NULL,                  -- "Asia/Seoul" (EVENT_META에서)
  adapter     text NOT NULL,                  -- kcr | icr | gbcc | generic
  blob_url    text NOT NULL,
  status      text NOT NULL DEFAULT 'parsing',-- parsing | ready | failed
  created_at  timestamptz DEFAULT now()
);

CREATE TABLE records (                        -- README의 record dict + conf_id
  id          bigserial PRIMARY KEY,
  conf_id     bigint REFERENCES conferences ON DELETE CASCADE,
  person      text, affiliation text, role text,
  is_primary_author boolean,
  date_raw    text, time_raw text,            -- 원문 보존
  starts_at   timestamptz, ends_at timestamptz, -- tz 반영해 파생 (푸시 예약용)
  room        text, session_code text, session_title text, talk_title text,
  page        int, authors_all jsonb
);
CREATE INDEX ON records (conf_id);

CREATE TABLE subscriptions (
  id          bigserial PRIMARY KEY,
  conf_id     bigint REFERENCES conferences ON DELETE CASCADE,
  query_name  text NOT NULL,                  -- 검색한 이름 (저장되는 유일한 개인정보)
  endpoint    text NOT NULL,                  -- Web Push endpoint
  p256dh      text NOT NULL, auth text NOT NULL,
  offsets_min int[] NOT NULL DEFAULT '{60,10}',
  created_at  timestamptz DEFAULT now(),
  UNIQUE (endpoint, conf_id, query_name)
);

CREATE TABLE scheduled_pushes (
  id          bigserial PRIMARY KEY,
  sub_id      bigint REFERENCES subscriptions ON DELETE CASCADE,
  record_id   bigint REFERENCES records ON DELETE CASCADE,
  fire_at     timestamptz NOT NULL,
  qstash_id   text,                           -- 취소용
  status      text NOT NULL DEFAULT 'scheduled' -- scheduled|sent|failed|cancelled
);
```

## 4. API 스펙

| 엔드포인트 | 요청 | 동작 |
|---|---|---|
| `POST /api/upload-url` | `{filename, sha256}` | 해시가 이미 있으면 `{confId, cached: true}` 즉시 반환(재업로드 생략). 없으면 Blob client-upload 토큰 발급 |
| `POST /api/parse` | `{blobUrl, sha256}` (업로드 콜백) | `_detect_adapter` → `parse()` → `normalize_records()` → DB. 멱등(해시 기준) |
| `GET /api/search` | `?conf=ID&name=…&threshold=80` 또는 `&affiliation=…` | `core.search.matcher.matches()` 를 DB 레코드에 적용. 결과 = 기존 record 형식 JSON |
| `POST /api/subscribe` | `{confId, name, pushSubscription, offsetsMin}` | 히트된 미래 세션 × 오프셋마다 QStash `publish(delay=…)` → `scheduled_pushes` 기록 |
| `POST /api/push` | QStash 웹훅 (Upstash-Signature 검증 필수) | `pywebpush`로 발송. 410 Gone이면 구독 삭제 + 잔여 예약 취소 |
| `GET /api/ics` | `?conf=ID&name=…` | 기존 `ics_exporter` 재사용 — 캘린더 알람 이중화 |
| `DELETE /api/subscribe` | `{subId}` | 예약 일괄 취소 (QStash messages delete) |

푸시 페이로드 예: `{"title":"⏰ 10분 후 발표","body":"14:00–14:20 Barahona 4\n★ AI and radiology: Turning crisis…","url":"/conf/12?name=Sung+Il+Hwang"}` → 서비스워커 `showNotification`, 탭하면 결과 화면.

## 5. 시간대 처리

- `starts_at`은 파싱 시 `EVENT_META`의 tz로 로컬라이즈해 UTC 저장. QStash 예약은 UTC 절대시각.
- 사용자가 학회 현지에 있든 한국에 있든 발송 시각은 동일(세션 실제 시작 기준). 표시만 브라우저 로컬 + 현지시각 병기.
- 과거 세션은 예약 생략. date 파싱 실패 레코드(`date_raw`만 있음)는 푸시 불가로 표시하고 .ics/화면 검색은 정상 제공.

## 6. 공유 캐시 & 프라이버시

- **공유 단위 = PDF 해시.** 동료가 이미 올린 KCR 프로그램북이면 업로드 화면에서 "이미 파싱됨 → 바로 검색"으로 스킵. 학회 목록 페이지(`/`)에 ready 상태 학회 나열 — 링크만 알면 접근 가능(로그인 없음).
- 저장되는 개인 데이터는 **푸시 구독의 query_name뿐.** 구독 관리 화면에서 본인 기기 구독만 보임(endpoint 기준). 학회 레코드 자체는 공개 프로그램북 내용.
- 업로드 남용 방지(v1 최소): 파일 크기 상한 200MB, MIME=application/pdf 검사, 시간당 업로드 rate limit (Upstash Ratelimit).

## 7. iOS PWA 온보딩 (가장 큰 UX 리스크)

- iPhone Safari: **홈 화면에 추가된 PWA에서만** 푸시 권한 요청 가능 (iOS 16.4+).
- "알림 받기" 버튼 클릭 시 standalone 모드 감지(`display-mode: standalone`) → 아니면 공유 시트 → "홈 화면에 추가" 안내 오버레이를 먼저 표시.
- 실패 대비 이중화: 같은 화면에 "📅 캘린더에 추가(.ics)" 버튼 상시 노출 — 캘린더 알람은 인프라 없이 동작하는 기존 기능.

## 8. 한도·비용 (무료 티어 기준, 대략치)

| 서비스 | 무료 한도(약) | 이 서비스 사용량 예상 |
|---|---|---|
| Vercel Hobby | 함수 실행 월 상당량, maxDuration ~300s | 파싱은 학회당 1회뿐 — 여유 |
| Vercel Blob | ~1GB 저장 | PDF 3–5권 ≈ 300MB. 파싱 완료 후 원본 삭제 옵션으로 절약 가능 |
| Neon | 0.5GB 저장 | records 수만 행 ≈ 수십 MB — 여유 |
| QStash | 500 msg/일 | 구독 1건 ≈ 세션 수 × 오프셋 2 ≈ 10–60건, 일회성 — 여유 |

예상 비용 **0원**으로 시작. 동료 수십 명 규모까지 무료 티어로 감당 가능.

## 9. 리스크 & 착수 전 검증 항목

1. ~~[스트레스 테스트] GBCC 76MB 파싱~~ → **검증 완료 (2026-07-16, 로컬 측정):** GBCC 76MB = 6.6–8.6s / 피크 RSS 199MB (records 2,505), KCR = 1.7s (2,719), ICR = 2.5s (310). Vercel 서버리스 한도(수 분 / 2GB) 대비 충분한 여유 — 파싱 분리 불필요. 서버리스 콜드스타트 + Blob 다운로드를 더해도 학회당 1회 20–30s 예상.
2. **pymupdf 번들 크기** — Python 함수 250MB(압축 해제) 한도 내인지 `vercel build`로 확인.
3. **generic 어댑터 품질** — 미지원 학회 PDF는 "지원 학회 아님, 결과 부정확 가능" 배지 필수. Phase 3에서 LLM 보조 파서(해시당 1회 Claude API 호출)로 보완.
4. **콜드 스타트** — 검색 API는 DB만 조회하므로 파서 import 불필요하게 분리(파싱 함수와 검색 함수의 의존성 분리).

## 10. 마일스톤

- **M1 — 웹 MVP:** 업로드→파싱→검색→.ics 다운로드. 푸시 없음. (데스크톱 앱의 웹판; core 재사용 검증이 목적)
- **M2 — 푸시:** PWA manifest + 서비스워커 + subscribe/push + QStash. iOS 온보딩 오버레이 포함.
- **M3 — 공유:** 학회 목록/캐시 UX, 구독 관리 화면, rate limit, (옵션) Telegram 채널, LLM generic 보강.
