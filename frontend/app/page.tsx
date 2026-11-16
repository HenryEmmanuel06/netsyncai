import Link from "next/link";
import { ArrowRight, Boxes, RefreshCw, Search, Share2, Zap } from "lucide-react";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between px-8 py-5">
        <div className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-[#8b5cf6] to-[#5f32d6]">
            <Boxes size={18} className="text-white" />
          </span>
          <span className="font-semibold">NetSync AI</span>
        </div>
        <Link href="/login" className="btn btn-ghost">Sign in</Link>
      </header>

      <section className="mx-auto flex max-w-2xl flex-1 flex-col items-center justify-center gap-6 px-6 text-center">
        <h1 className="text-5xl font-bold leading-tight tracking-tight">
          Your files, on{" "}
          <span className="bg-gradient-to-r from-[#a78bfa] to-[#7c4dff] bg-clip-text text-transparent">
            every computer
          </span>
        </h1>
        <p className="max-w-md text-[var(--color-text-dim)]">
          Browse, transfer, share and synchronize files across all your PCs —
          and your colleagues' — from one dashboard. Powered by an AI assistant
          that turns words into actions.
        </p>
        <div className="flex gap-3">
          <Link href="/login" className="btn btn-primary !px-6 !py-3">
            Get started <ArrowRight size={15} />
          </Link>
        </div>
        <div className="mt-8 grid grid-cols-2 gap-3 text-left sm:grid-cols-4">
          {[
            { icon: <Search size={16} />, t: "Search everywhere", s: "Every computer at once" },
            { icon: <RefreshCw size={16} />, t: "Live sync", s: "Two-way, real-time" },
            { icon: <Share2 size={16} />, t: "Share & permissions", s: "Colleague access control" },
            { icon: <Zap size={16} />, t: "AI automation", s: "Natural language tasks" },
          ].map((f) => (
            <div key={f.t} className="card p-4">
              <span className="text-[var(--color-accent)]">{f.icon}</span>
              <div className="mt-2 text-sm font-semibold">{f.t}</div>
              <div className="text-xs text-[var(--color-text-dim)]">{f.s}</div>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
