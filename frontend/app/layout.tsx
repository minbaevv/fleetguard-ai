import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FleetGuard AI",
  description: "Фотофиксация состояния кузова до и после смены",
};

export const viewport: Viewport = {
  themeColor: "#05070f",
  colorScheme: "dark",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru" data-scroll-behavior="smooth">
      <body className="min-h-screen antialiased">
        <div className="site-bg" aria-hidden="true">
          <div className="site-grid" />
          <span className="orb orb-a" />
          <span className="orb orb-b" />
          <span className="orb orb-c" />
        </div>
        {children}
      </body>
    </html>
  );
}
