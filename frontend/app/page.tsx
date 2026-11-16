import Link from "next/link";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-8">
      <h1 className="text-4xl font-bold tracking-tight">
        Net<span className="text-[var(--color-primary)]">Sync</span> AI
      </h1>
      <p className="max-w-md text-center text-[var(--color-text-dim)]">
        Intelligent distributed file management and real-time synchronization
        across your networked computers.
      </p>
      <div className="flex gap-4">
        <Link
          href="/login"
          className="rounded-lg bg-[var(--color-primary)] px-5 py-2.5 font-medium text-white hover:bg-[var(--color-primary-hover)]"
        >
          Sign in
        </Link>
        <Link
          href="/assistant"
          className="rounded-lg border border-[var(--color-border)] px-5 py-2.5 hover:bg-[var(--color-surface-2)]"
        >
          Open app
        </Link>
      </div>
    </main>
  );
}
