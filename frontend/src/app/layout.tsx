import type { Metadata } from "next";
import Link from "next/link";
import ModePill from "@/components/ModePill";
import "./globals.css";

export const metadata: Metadata = {
  title: "ReadyTrader | AI Forex Trading",
  description: "Dashboard for the ReadyTrader-FOREX MCP server: the paper account and trade approvals",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <div className="layout-root">
          <aside className="sidebar">
            <div className="logo-container">
              <span className="logo-text">READY<span>TRADER</span></span>
            </div>
            <nav className="main-nav">
              <Link href="/" className="nav-item active">Dashboard</Link>
            </nav>
          </aside>
          <main className="content">
            <header className="top-bar">
              <div className="status-indicators">
                <ModePill />
              </div>
              <div className="user-profile">
                <span>Agent Zero</span>
              </div>
            </header>
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
