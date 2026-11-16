export function PlaceholderPage({
  title,
  phase,
  description,
}: {
  title: string;
  phase: string;
  description: string;
}) {
  return (
    <div className="mx-auto max-w-2xl pt-16">
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="mt-2 text-[var(--color-text-dim)]">{description}</p>
      <div className="card mt-6 p-4 text-sm text-[var(--color-text-dim)]">
        Scheduled for <span className="text-[var(--color-primary)]">{phase}</span>.
        See <code>docs/ARCHITECTURE.md</code> for the implementation plan.
      </div>
    </div>
  );
}
