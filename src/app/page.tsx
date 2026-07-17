"use client";

import { upload } from "@vercel/blob/client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { Conference } from "@/lib/types";

async function sha256Hex(file: File): Promise<string> {
  const buf = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export default function HomePage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [confs, setConfs] = useState<Conference[]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);

  useEffect(() => {
    fetch("/api/conferences")
      .then((r) => r.json())
      .then((d) => setConfs(d.conferences ?? []))
      .catch(() => {});
  }, []);

  async function handleFile(file: File) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("PDF 파일만 업로드할 수 있습니다.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      setStatus("파일 확인 중… (해시 계산)");
      const sha256 = await sha256Hex(file);

      // 공유 캐시: 동료가 이미 올린 PDF면 업로드/파싱 없이 바로 이동 (설계 §6)
      const cached = await fetch(`/api/parse?sha256=${sha256}`).then((r) => r.json());
      if (cached.exists && cached.conference?.status === "ready") {
        setStatus("이미 파싱된 학회입니다 — 바로 이동합니다.");
        router.push(`/conf/${cached.conference.id}`);
        return;
      }

      setStatus("업로드 중… (수십 MB면 잠시 걸립니다)");
      const blob = await upload(file.name, file, {
        access: "public",
        handleUploadUrl: "/api/upload",
      });

      setStatus("파싱 중… (학회당 최초 1회, 약 10초)");
      const res = await fetch("/api/parse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: blob.url, sha256, filename: file.name }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? `파싱 실패 (HTTP ${res.status})`);
      router.push(`/conf/${data.conference.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <h1>Abstract Searcher</h1>
      <p className="subtitle">학회 프로그램 PDF에서 내 발표·좌장 일정을 찾아 캘린더로 보내세요.</p>

      <div
        className={`dropzone${drag ? " drag" : ""}`}
        onClick={() => !busy && inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          const f = e.dataTransfer.files?.[0];
          if (f && !busy) void handleFile(f);
        }}
      >
        <strong>프로그램북 PDF를 여기에 끌어다 놓거나 클릭해서 선택</strong>
        <div className="conf-meta">KCR · ICR · GBCC 지원, 그 외 학회는 베스트에포트 (최대 200MB)</div>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void handleFile(f);
            e.target.value = "";
          }}
        />
        {status && <div className="status">{status}</div>}
        {error && <div className="status error">{error}</div>}
      </div>

      <div className="toolbar">
        <h2 style={{ margin: 0, fontSize: "1.1rem" }}>등록된 학회</h2>
        <Link href="/subs">🔔 내 알림 관리</Link>
      </div>
      {confs.length === 0 && <div className="card conf-meta">아직 등록된 학회가 없습니다.</div>}
      {confs.map((c) => (
        <div className="card conf-item" key={c.id}>
          <div>
            {c.status === "ready" ? (
              <>
                <Link href={`/conf/${c.id}`}>{c.title}</Link>
                {c.adapter === "generic" && <span className="badge other"> 일반 파서</span>}
                {c.adapter === "llm" && <span className="badge other"> AI 파서</span>}
              </>
            ) : (
              <span>
                {c.title}{" "}
                <span className={`badge status-${c.status}`}>
                  {c.status === "parsing" ? "파싱 중" : "실패"}
                </span>
              </span>
            )}
            <div className="conf-meta">
              {[c.location, c.tz, `${c.recordCount ?? 0}개 레코드`].filter(Boolean).join(" · ")}
            </div>
          </div>
        </div>
      ))}
    </main>
  );
}
