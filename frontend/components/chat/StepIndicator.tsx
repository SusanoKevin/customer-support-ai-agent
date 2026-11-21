import type { Step } from "@/lib/conversation";

const ICON: Record<Step["state"], string> = { started: "", completed: "✓", failed: "!" };

const DOT: Record<Step["state"], string> = {
  started: "border-2 border-accent border-t-transparent animate-spin",
  completed: "bg-ok/15 text-ok",
  failed: "bg-bad/15 text-bad",
};

export function StepIndicator({ steps, live }: { steps: Step[]; live: boolean }) {
  if (steps.length === 0) return null;
  return (
    <ol className="space-y-1 text-xs text-muted" aria-label="Agent progress" aria-live="polite">
      {steps.map((s, i) => (
        <li key={`${s.step}-${i}`} className="flex items-center gap-2">
          <span
            className={`flex size-4 items-center justify-center rounded-full text-[10px] font-bold ${DOT[s.state]}`}
            aria-hidden
          >
            {ICON[s.state]}
          </span>
          <span className={s.state === "started" && live ? "text-fg" : undefined}>
            {s.label}
            {s.state === "failed" && " (failed)"}
          </span>
        </li>
      ))}
    </ol>
  );
}
