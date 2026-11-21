import type { ToolCall } from "@/lib/conversation";

export function ToolCard({ tool }: { tool: ToolCall }) {
  return (
    <details className="group rounded-lg border border-line bg-surface-2 text-xs">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2">
        <span className={`size-2 rounded-full ${tool.ok ? "bg-ok" : "bg-bad"}`} aria-hidden />
        <span className="font-mono font-medium">{tool.name}</span>
        <span className="text-muted">{tool.ok ? "succeeded" : "failed"}</span>
        <span className="ml-auto text-muted transition group-open:rotate-90" aria-hidden>
          ›
        </span>
      </summary>
      <div className="grid gap-2 border-t border-line px-3 py-2">
        <Payload title="Input" value={tool.input} />
        <Payload title="Output" value={tool.output} />
      </div>
    </details>
  );
}

function Payload({ title, value }: { title: string; value: unknown }) {
  return (
    <div>
      <div className="mb-1 font-medium text-muted">{title}</div>
      <pre className="max-h-48 overflow-auto rounded bg-surface p-2 font-mono text-[11px] leading-relaxed">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}
