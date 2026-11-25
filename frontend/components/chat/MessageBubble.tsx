import { citedSources, splitCitations, type Source } from "@/lib/citations";
import type { Message } from "@/lib/conversation";
import { EscalationBanner } from "./EscalationBanner";
import { StepIndicator } from "./StepIndicator";
import { ToolCard } from "./ToolCard";

interface MessageBubbleProps {
  message: Message;
  live: boolean;
  onRetry?: () => void;
}

export function MessageBubble({ message, live, onRetry }: MessageBubbleProps) {
  if (message.role === "user") {
    return (
      <div className="flex flex-col items-end gap-1">
        {message.via === "voice" && <span className="text-[11px] text-muted">Said in voice</span>}
        <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-accent px-4 py-2 text-sm text-on-accent">
          {message.text}
        </p>
      </div>
    );
  }
  const streaming = live && message.steps.some((s) => s.step === "respond" && s.state === "started");
  const sources = citedSources(message.text, message.tools);
  return (
    <div className="flex max-w-[92%] flex-col gap-2">
      <StepIndicator steps={message.steps} live={live} />
      {message.tools.length > 0 && (
        <div className="grid gap-1.5">
          {message.tools.map((t, i) => (
            <ToolCard key={`${t.name}-${i}`} tool={t} />
          ))}
        </div>
      )}
      {(message.text || streaming) && (
        <p className="whitespace-pre-wrap rounded-2xl rounded-bl-sm bg-surface-2 px-4 py-2 text-sm leading-relaxed">
          <AnswerText text={message.text} sources={sources} />
          {live && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-muted align-middle" aria-hidden />}
        </p>
      )}
      {!live && sources.length > 0 && <SourceList sources={sources} />}
      {message.escalation && <EscalationBanner escalation={message.escalation} />}
      {message.error && (
        <div role="alert" className="flex items-center gap-3 rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-xs">
          <span>{message.error.message}</span>
          {message.error.retryable && onRetry && (
            <button
              onClick={onRetry}
              className="ml-auto rounded-md bg-bad px-2 py-1 font-medium text-white hover:opacity-90"
            >
              Retry
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function AnswerText({ text, sources }: { text: string; sources: Source[] }) {
  return splitCitations(text).map((s, i) => {
    if (s.kind === "text") return <span key={i}>{s.value}</span>;
    const n = sources.findIndex((src) => src.id === s.value) + 1;
    return (
      <sup key={i} title={sources[n - 1]?.title} className="mx-0.5 text-[10px] font-medium text-muted">
        [{n}]
      </sup>
    );
  });
}

/** Plain text, not links: the sections live in the policy documents, not on a page. */
function SourceList({ sources }: { sources: Source[] }) {
  return (
    <div className="px-1 text-[11px] text-muted">
      <p className="font-medium">Sources</p>
      <ol className="mt-0.5 space-y-0.5">
        {sources.map((s, i) => (
          <li key={s.id}>
            [{i + 1}] {s.title} <span className="opacity-70">({s.doc} policy)</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
