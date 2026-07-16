"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { pushSupported } from "@/lib/push";

type Sub = {
  subId: number;
  confId: number;
  confTitle: string;
  query: string;
  offsetsMin: number[];
  createdAt: string;
  upcoming: number;
  sent: number;
};

function offsetLabel(min: number): string {
  if (min % 1440 === 0) return `${min / 1440}일 전`;
  if (min % 60 === 0) return `${min / 60}시간 전`;
  return `${min}분 전`;
}

export default function SubsPage() {
  const [subs, setSubs] = useState<Sub[] | null>(null);
  const [endpoint, setEndpoint] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    (async () => {
      try {
        if (!pushSupported()) {
          setMsg("이 브라우저는 웹 푸시를 지원하지 않습니다. (iPhone은 홈 화면 앱에서 열어주세요)");
          setSubs([]);
          return;
        }
        const reg = await navigator.serviceWorker.register("/sw.js");
        const sub = await reg.pushManager.getSubscription();
        if (!sub) {
          setMsg("이 기기에서 구독한 알림이 없습니다. 학회 검색 후 🔔 버튼으로 구독하세요.");
          setSubs([]);
          return;
        }
        setEndpoint(sub.endpoint);
        const res = await fetch("/api/subs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ endpoint: sub.endpoint }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error ?? `HTTP ${res.status}`);
        setSubs(data.subscriptions);
        if (data.subscriptions.length === 0) {
          setMsg("이 기기에서 구독한 알림이 없습니다. 학회 검색 후 🔔 버튼으로 구독하세요.");
        }
      } catch (e) {
        setMsg(e instanceof Error ? e.message : String(e));
        setSubs([]);
      }
    })();
  }, []);

  async function remove(subId: number) {
    const res = await fetch("/api/subs", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subId, endpoint }),
    });
    if (res.ok) {
      setSubs((prev) => (prev ? prev.filter((s) => s.subId !== subId) : prev));
    }
  }

  return (
    <main>
      <h1><Link href="/">Abstract Searcher</Link></h1>
      <p className="subtitle">🔔 이 기기의 알림 구독 관리</p>

      {subs === null && <div className="card conf-meta">불러오는 중…</div>}
      {msg && <div className="card conf-meta">{msg}</div>}

      {subs?.map((s) => (
        <div className="card conf-item" key={s.subId}>
          <div>
            <Link href={`/conf/${s.confId}?q=${encodeURIComponent(s.query)}`}>
              {s.confTitle}
            </Link>{" "}
            — <strong>{s.query}</strong>
            <div className="conf-meta">
              {s.offsetsMin.map(offsetLabel).join(" · ")} 알림 · 예정 {s.upcoming}건 · 발송됨 {s.sent}건
            </div>
          </div>
          <button className="btn-secondary" style={{ background: "var(--card)" }} onClick={() => void remove(s.subId)}>
            해제
          </button>
        </div>
      ))}
    </main>
  );
}
