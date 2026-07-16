-- Abstract Searcher web service schema (Neon Postgres).
-- M1 uses conferences + records; subscriptions + scheduled_pushes are M2 (push).
-- Apply: python scripts/init_webdb.py  (reads DATABASE_URL)

CREATE TABLE IF NOT EXISTS conferences (
  id          bigserial PRIMARY KEY,
  sha256      char(64) UNIQUE NOT NULL,        -- 공유 캐시 키
  title       text NOT NULL,                   -- "KCR 2025" (EVENT_META.event_name)
  location    text NOT NULL DEFAULT '',
  tz          text NOT NULL DEFAULT 'UTC',     -- EVENT_META.event_timezone
  adapter     text NOT NULL DEFAULT 'generic', -- kcr | icr | gbcc | generic
  blob_url    text NOT NULL,
  status      text NOT NULL DEFAULT 'parsing', -- parsing | ready | failed
  error       text,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS records (
  id          bigserial PRIMARY KEY,
  conf_id     bigint NOT NULL REFERENCES conferences ON DELETE CASCADE,
  person      text NOT NULL DEFAULT '',
  affiliation text NOT NULL DEFAULT '',
  role        text NOT NULL DEFAULT 'unknown',
  is_primary_author boolean NOT NULL DEFAULT false,
  date_raw    text NOT NULL DEFAULT '',        -- "Sep. 26 (Fri)" 원문 보존
  time_raw    text NOT NULL DEFAULT '',        -- "14:00-14:20"
  starts_at   timestamptz,                     -- tz 반영 파생값 (푸시 예약용, 파싱 실패 시 NULL)
  ends_at     timestamptz,
  room        text NOT NULL DEFAULT '',
  session_code  text NOT NULL DEFAULT '',
  session_title text NOT NULL DEFAULT '',
  talk_title  text NOT NULL DEFAULT '',
  page        int NOT NULL DEFAULT 0,
  authors_all jsonb NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS records_conf_idx ON records (conf_id);

-- ── M2 (push) ────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS subscriptions (
  id          bigserial PRIMARY KEY,
  conf_id     bigint NOT NULL REFERENCES conferences ON DELETE CASCADE,
  query_name  text NOT NULL,
  endpoint    text NOT NULL,
  p256dh      text NOT NULL,
  auth        text NOT NULL,
  offsets_min int[] NOT NULL DEFAULT '{60,10}',
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (endpoint, conf_id, query_name)
);

CREATE TABLE IF NOT EXISTS scheduled_pushes (
  id          bigserial PRIMARY KEY,
  sub_id      bigint NOT NULL REFERENCES subscriptions ON DELETE CASCADE,
  record_id   bigint NOT NULL REFERENCES records ON DELETE CASCADE,
  fire_at     timestamptz NOT NULL,
  qstash_id   text,
  status      text NOT NULL DEFAULT 'scheduled' -- scheduled | sent | failed | cancelled
);
