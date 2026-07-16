"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ensurePushSubscription, isIOS, isStandalone } from "@/lib/push";
import type { Conference, Hit } from "@/lib/types";

const ROLE_BADGE: Record<string, string> = {
  speaker: "speaker",
  chair: "chair",
  discussant: "discussant",
};

const subKey = (conf: string, q: string) => `push-sub:${conf}:${q}`;

export default function ConferencePage() {
  const { id } = useParams<{ id: string }>();
  const [q, setQ] = useState("");
  const [mode, setMode] = useState<"name" | "affiliation">("name");
  const [threshold, setThreshold] = useState(80);
  const [sort, setSort] = useState<"score" | "time">("time");
  const [conf, setConf] = useState<Conference | null>(null);
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [subscribed, setSubscribed] = useState(false);
  const [subBusy, setSubBusy] = useState(false);
  const [subMsg, setSubMsg] = useState("");
  const [showIosGuide, setShowIosGuide] = useState(false);

  useEffect(() => {
    if (q.trim()) setSubscribed(!!localStorage.getItem(subKey(id, q.trim())));
  }, [id, q]);

  async function toggleNotify() {
    const query = q.trim();
    if (!query || !hits) return;
    setSubBusy(true);
    setSubMsg("");
    try {
      if (subscribed) {
        const saved = JSON.parse(localStorage.getItem(subKey(id, query)) ?? "{}");
        await fetch("/api/subscribe", {
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ confId: Number(id), q: query, endpoint: saved.endpoint }),
        });
        localStorage.removeItem(subKey(id, query));
        setSubscribed(false);
        setSubMsg("알림을 해제했습니다.");
        return;
      }
      // iOS Safari can only ask notification permission inside an installed PWA (design §7)
      if (isIOS() && !isStandalone()) {
        setShowIosGuide(true);
        return;
      }
      const subscription = await ensurePushSubscription();
      const res = await fetch("/api/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          confId: Number(id), q: query, mode, threshold,
          offsetsMin: [60, 10], subscription,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? `구독 실패 (HTTP ${res.status})`);
      localStorage.setItem(subKey(id, query), JSON.stringify({ endpoint: subscription.endpoint }));
      setSubscribed(true);
      setSubMsg(
        data.reminders > 0
          ? `세션 ${data.sessions}건 × 시작 60분·10분 전 알림 ${data.reminders}건 예약 완료`
          : "예약할 미래 세션이 없습니다 (지난 학회이거나 시간 파싱 불가)."
      );
    } catch (e) {
      setSubMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSubBusy(false);
    }
  }

  const searchUrl = (base: string) =>
    `${base}?conf=${id}&q=${encodeURIComponent(q)}&mode=${mode}&threshold=${threshold}`;

  async function search(e?: React.FormEvent) {
    e?.preventDefault();
    if (!q.trim()) return;
    setBusy(true);
    setError("");
    try {
      const res = await fetch(searchUrl("/api/search"));
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? `검색 실패 (HTTP ${res.status})`);
      setConf(data.conference);
      setHits(data.hits);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setHits(null);
    } finally {
      setBusy(false);
    }
  }

  const sorted = hits
    ? [...hits].sort((a, b) =>
        sort === "time"
          ? (a.startsAt ?? "9999") < (b.startsAt ?? "9999") ? -1 : 1
          : b._score - a._score
      )
    : null;

  return (
    <main>
      <h1><Link href="/">Abstract Searcher</Link></h1>
      <p className="subtitle">
        {conf ? `${conf.title} — ${conf.location} (${conf.tz})` : `학회 #${id}`}
      </p>

      <form className="card search-form" onSubmit={search}>
        <div className="search-row">
          <input
            type="text"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={mode === "name" ? "이름 (예: Sung Il Hwang)" : "소속 (예: Seoul National University Bundang)"}
            autoFocus
          />
          <button type="submit" disabled={busy || !q.trim()}>
            {busy ? "검색 중…" : "검색"}
          </button>
        </div>
        <div className="search-row">
          <label className="radio">
            <input type="radio" checked={mode === "name"} onChange={() => setMode("name")} /> 이름
          </label>
          <label className="radio">
            <input type="radio" checked={mode === "affiliation"} onChange={() => setMode("affiliation")} /> 소속
          </label>
          <label className="radio">
            정확도 {threshold}
            <input
              type="range" min={50} max={100} step={5} value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
            />
          </label>
        </div>
      </form>

      {error && <div className="card status error">{error}</div>}

      {sorted && (
        <>
          <div className="toolbar">
            <div>
              <strong>{sorted.length}건</strong>
              <span className="conf-meta"> — {q}</span>
            </div>
            <div className="search-row">
              <select value={sort} onChange={(e) => setSort(e.target.value as "score" | "time")}>
                <option value="time">시간순</option>
                <option value="score">정확도순</option>
              </select>
              {sorted.length > 0 && (
                <>
                  <a className="btn btn-secondary" href={searchUrl("/api/ics")}>
                    📅 캘린더(.ics)
                  </a>
                  <button onClick={toggleNotify} disabled={subBusy}>
                    {subBusy ? "처리 중…" : subscribed ? "🔕 알림 해제" : "🔔 세션 알림 받기"}
                  </button>
                </>
              )}
            </div>
          </div>
          {subMsg && <div className="card conf-meta">{subMsg}</div>}

          {showIosGuide && (
            <div className="overlay" onClick={() => setShowIosGuide(false)}>
              <div className="card overlay-card" onClick={(e) => e.stopPropagation()}>
                <h3 style={{ marginTop: 0 }}>iPhone 알림 설정 방법</h3>
                <p>iPhone은 홈 화면에 추가된 앱에서만 알림을 받을 수 있습니다:</p>
                <ol>
                  <li>Safari 하단의 <strong>공유 버튼</strong> (⬆️) 탭</li>
                  <li><strong>"홈 화면에 추가"</strong> 선택</li>
                  <li>홈 화면의 <strong>Abstracts</strong> 아이콘으로 다시 열기</li>
                  <li>같은 검색 후 <strong>🔔 세션 알림 받기</strong> 다시 탭</li>
                </ol>
                <p className="conf-meta">
                  캘린더 알림이 더 편하면 📅 캘린더(.ics) 버튼으로 폰 캘린더에 넣어도 됩니다.
                </p>
                <button onClick={() => setShowIosGuide(false)}>확인</button>
              </div>
            </div>
          )}

          {sorted.length === 0 && (
            <div className="card conf-meta">
              결과가 없습니다. 정확도를 낮추거나 이름 표기를 바꿔보세요 (예: 성만, 영문 전체).
            </div>
          )}

          {sorted.map((h, i) => (
            <div className="card hit" key={h.id ?? i}>
              <div className="hit-when">
                {[h.date, h.time, h.room].filter(Boolean).join(" · ") || "시간 미상"}
              </div>
              <div className="hit-title">
                <span className={`badge ${ROLE_BADGE[h.role] ?? "other"}`}>
                  {h.is_primary_author ? "★ " : ""}{h.role}
                </span>
                {h.talk_title || h.session_title}
              </div>
              <div className="hit-meta">
                {[
                  h.person,
                  h.affiliation,
                  [h.session_code, h.session_title].filter(Boolean).join(" — "),
                  `p.${h.page}`,
                  `score ${h._score}`,
                ].filter(Boolean).join(" · ")}
              </div>
            </div>
          ))}
        </>
      )}
    </main>
  );
}
