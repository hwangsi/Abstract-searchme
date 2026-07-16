"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import type { Conference, Hit } from "@/lib/types";

const ROLE_BADGE: Record<string, string> = {
  speaker: "speaker",
  chair: "chair",
  discussant: "discussant",
};

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
                <a className="btn btn-secondary" href={searchUrl("/api/ics")}>
                  📅 캘린더(.ics)
                </a>
              )}
            </div>
          </div>

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
