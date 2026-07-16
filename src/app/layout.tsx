import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Abstract Searcher",
  description: "학회 프로그램 PDF에서 내 발표 일정 찾기",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <div className="container">{children}</div>
      </body>
    </html>
  );
}
