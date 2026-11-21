import { splitCitations } from "@/lib/citations";
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
          <AnswerText text={message.text} />
          {live && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-muted align-middle" aria-hidden />}
        </p>
      )}
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

function AnswerText({ text }: { text: string }) {
  return splitCitations(text).map((s, i) =>
    s.kind === "text" ? (
      <span key={i}>{s.value}</span>
    ) : (
      <sup
        key={i}
        title={`Policy source ${s.value}`}
        className="mx-0.5 rounded bg-accent/15 px-1 font-mono text-[10px] text-accent"
      >
        {s.value.split(":")[0]}
      </sup>
    ),
  );
}
