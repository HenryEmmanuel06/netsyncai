import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NetSync AI",
  description: "AI-driven distributed file management and synchronization",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
