"use client";
import { useEffect, useRef } from "react";
import type { VoiceLine, VoiceStatus } from "@/lib/voice/voiceState";
import type { VoiceCall } from "./useVoiceCall";
import { Waveform } from "./Waveform";

const STATUS_LABEL: Record<VoiceStatus, string> = {
  idle: "Ready when you are",
  connecting: "Connecting...",
  listening: "Listening",
  checking: "Checking with the support agent...",
  speaking: "Speaking (talk to interrupt)",
  ended: "Call ended",
  error: "Voice stopped",
};

interface VoicePanelProps {
  call: VoiceCall;
  canStart: boolean;
}

export function VoicePanel({ call, canStart }: VoicePanelProps) {
  const { state, isActive, start, stop, getAnalyser } = call;
  const endRef = useRef<HTMLLIElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [state.lines]);

  const dotColor = isActive ? "animate-pulse bg-ok" : state.status === "error" ? "bg-bad" : "bg-muted";
  const tokens = state.usage.promptTokens + state.usage.responseTokens;

  return (
    <section aria-label="Voice" className="flex min-h-0 flex-1 flex-col">
      <div className="border-b border-line p-3">
        <div className="flex items-center gap-2">
          <span aria-hidden className={`size-2.5 rounded-full ${dotColor}`} />
          <p className="text-sm font-medium" aria-live="polite">
            {STATUS_LABEL[state.status]}
          </p>
          <div className="ml-auto">
            {isActive ? (
              <button onClick={stop} className="h-9 rounded-xl bg-bad px-3 text-sm font-medium text-on-accent">
                End call
              </button>
            ) : (
              <button
                onClick={start}
                disabled={!canStart}
                className="h-9 rounded-xl bg-accent px-3 text-sm font-medium text-on-accent disabled:opacity-40"
              >
                {state.status === "idle" ? "Start voice" : "Start again"}
              </button>
            )}
          </div>
        </div>
        <Waveform getAnalyser={getAnalyser} label={state.status === "speaking" ? "Assistant audio" : "Your microphone"} />
        {state.error && (
          <p role="alert" className="mt-1 text-xs text-bad">
            {state.error.message}
          </p>
        )}
        {state.notice && <p className="mt-1 text-xs text-warn">{state.notice}</p>}
        <p className="mt-1 text-[11px] leading-snug text-muted">
          Voice uses the same support agent as the chat, so account and refund steps show in the chat and the trace.
          {state.usage.reports > 0 && ` Tokens this call: ${tokens.toLocaleString()}.`}
        </p>
      </div>
      <ol className="flex flex-1 flex-col gap-3 overflow-y-auto p-3" aria-label="Voice transcript">
        {state.lines.length === 0 && <li className="text-center text-xs text-muted">What you and the assistant say appears here.</li>}
        {state.lines.map((line) => (
          <TranscriptLine key={line.id} line={line} />
        ))}
        <li ref={endRef} aria-hidden />
      </ol>
    </section>
  );
}

function TranscriptLine({ line }: { line: VoiceLine }) {
  const isUser = line.role === "user";
  const bubble = isUser ? "rounded-br-sm bg-accent text-on-accent" : "rounded-bl-sm bg-surface-2";
  return (
    <li className={`flex ${isUser ? "justify-end" : ""}`}>
      <p className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm ${bubble} ${line.final ? "" : "opacity-70"}`}>
        {line.text}
        {line.interrupted && <span className="ml-1 text-xs text-muted">(interrupted)</span>}
      </p>
    </li>
  );
}
