# 웹 서비스 개발/배포 가이드 (M1)

설계: [WEB_SERVICE_DESIGN.md](WEB_SERVICE_DESIGN.md) · 스택: Next.js(App Router) + Vercel Python Functions + Neon Postgres + Vercel Blob

> **배포 상태 (2026-07-17, M2까지):** 프로덕션 https://abstract-searcher.vercel.app 가동 중.
> Vercel 프로젝트 `abstract-searcher` + Neon(`DATABASE_URL`) + Blob(`abstract-searcher-pdfs`)
> + Upstash QStash(Marketplace) 연결, GitHub 자동 배포(`vercel git connect`) 활성.
> VAPID 키/CRON_SECRET/PUSH_BASE_URL 환경변수 등록 완료.
> 검증 완료: ICR 2026 파싱·검색·ics E2E, 푸시 구독/해제, QStash→/api/push 전달(서명 검증, 200),
> 무서명 요청 401 거부, **실기기 수신 확인(2026-07-17, iPhone PWA/Apple Web Push,
> 테스트 학회로 60분·10분 전 알림 정시 도착)**. 테스트 데이터는 삭제됨.
> M3(2026-07-17): /subs 구독 관리, 알림 오프셋 커스터마이즈(10분~1일 전),
> 일반 파서 경고 배지, 신규 업로드 rate limit(10건/시). E2E 검증 완료.
> LLM 보조 파서 가동(2026-07-17): 미지원 학회는 Groq(llama-3.3-70b, 무료 티어)로
> 페이지 단위 추출 — `LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL` env로 프로바이더 교체 가능.
> KCR 대조 실측: 동일 페이지 인명 재현율 100%(45/45), 프로덕션 E2E 103 레코드.
> 한계: 미지원 학회는 timezone을 모르므로 UTC 가정 — 푸시 시각이 어긋날 수 있음(개선 후보).
> 미착수(사용자 결정 대기): Telegram 채널(봇 토큰 필요).

## 1회 셋업

1. **Vercel 프로젝트 생성** — 레포 루트가 프로젝트 루트 (Root Directory 설정 없음).
   Framework Preset: Next.js. `api/*.py`는 자동으로 Python 서버리스 함수가 됨.
2. **Neon Postgres** — [neon.tech](https://neon.tech) 무료 DB 생성 → 커넥션 문자열 복사.
   ```
   # 스키마 적용 (로컬에서 1회)
   pip install "psycopg[binary]"
   set DATABASE_URL=postgres://...        # PowerShell: $env:DATABASE_URL="..."
   python scripts/init_webdb.py
   ```
3. **Vercel Blob** — Vercel 대시보드 → Storage → Blob store 생성 → 프로젝트에 연결
   (`BLOB_READ_WRITE_TOKEN` 자동 주입).
4. **환경변수** — Vercel 프로젝트 Settings → Environment Variables에 `DATABASE_URL` 추가.

## 로컬 개발

```bash
npm install
npm i -g vercel && vercel link        # 최초 1회 — env를 로컬로 끌어옴
vercel env pull .env.local
npm run dev                           # = vercel dev (front + Python 함수 모두 구동)
```

`next dev`(= `npm run dev:front`)는 프론트만 뜨고 `/api/*.py`는 안 뜸 — 전체 흐름은 `vercel dev`로.

## 파일 맵

| 경로 | 역할 |
|---|---|
| `src/app/page.tsx` | 홈: 업로드(해시→캐시 확인→Blob→파싱) + 학회 목록 |
| `src/app/conf/[id]/page.tsx` | 검색(이름/소속, 정확도) + 결과 + .ics 다운로드 |
| `src/app/api/upload/route.ts` | Blob 클라이언트 업로드 토큰 (Node) |
| `api/parse.py` | GET: sha256 캐시 조회 / POST: 다운로드→`core.adapters.load_pdf`→DB |
| `api/search.py` | `core.search.matcher` 로 DB 레코드 검색 (pymupdf 미포함 — 콜드스타트 경량) |
| `api/ics.py` | `core.exporters.ics_exporter` 재사용 캘린더 내보내기 |
| `api/conferences.py` | 학회 목록 |
| `api/_lib/` | 함수 간 공유 코드 (함수로 노출 안 됨) |
| `db/schema.sql` | 스키마 (M2 push 테이블 포함) |

## 주의점

- **루트 `requirements.txt`는 데스크톱 앱용** (PySide6 포함). 웹 함수 의존성은
  `api/requirements.txt`이며, 루트 것은 `.vercelignore`로 배포에서 제외됨.
- Python 함수는 파일별로 개별 번들됨 — **함수 파일끼리 import 금지**, 공유 코드는
  `api/_lib/`에 (vercel.json `includeFiles`가 `core/**`와 `api/_lib/**`를 각 번들에 포함).
- 첫 배포에서 확인할 것: ① `api/requirements.txt`가 사용되는지(빌드 로그에 PySide6가
  보이면 안 됨) ② `includeFiles`로 `core/`가 함수에 포함됐는지 (안 되면 /api/parse가
  ImportError) ③ parse 함수 maxDuration(300s) 적용 여부.
- 업로드 정합성: parse.py가 다운로드한 파일의 sha256을 재검증하므로 클라이언트가
  거짓 해시로 다른 학회의 캐시를 오염시킬 수 없음.
