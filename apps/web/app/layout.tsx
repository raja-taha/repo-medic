import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "RepoMedic — Issue-to-Patch Agent",
  description:
    "Clone, diagnose, patch, and verify GitHub issues inside a sandboxed repair loop.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,700&family=IBM+Plex+Mono:wght@400;500&family=Manrope:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <div className="shell">
          <header className="site-header">
            <Link href="/" className="brand">
              Repo<span>Medic</span>
            </Link>
            <nav className="nav-links">
              <Link href="/tasks">Review queue</Link>
              <Link href="/#start">Start repair</Link>
            </nav>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}