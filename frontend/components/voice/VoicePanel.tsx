"use client";
import { useCallback, useEffect, useReducer, useRef } from "react";
import { VoiceSession } from "@/lib/voice/session";
import { initialVoice, voiceReducer, type VoiceLine, type VoiceStatus } from "@/lib/voice/voiceState";
import { Waveform } from "./Waveform";

const STATUS_LABEL: Record<VoiceStatus, string> = {
  idle: "Ready when you are",
  connecting: "Connecting...",
  listening: "Listening",
  speaking: "Speaking (talk to interrupt)",
  ended: "Call ended",
  error: "Voice stopped",
};

const ACTIVE: ReadonlySet<VoiceStatus> = new Set(["connecting", "listening", "speaking"]);

interface VoicePanelProps {
  sessionId: string;
}

export function VoicePanel({ sessionId }: VoicePanelProps) {
  const [state, dispatch] = useReducer(voiceReducer, undefined, initialVoice);
  const sessionRef = useRef<VoiceSession | null>(null);
  const statusRef = useRef(state.status);
  const endRef = useRef<HTMLDivElement>(null);
  const isActive = ACTIVE.has(state.status);

  useEffect(() => {
    statusRef.current = state.status;
  }, [state.status]);

  useEffect(() => () => sessionRef.current?.stop(), []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [state.lines]);

  const getAnalyser = useCallback(() => {
    const session = sessionRef.current;
    if (!session) return null;
    return statusRef.current === "speaking" ? session.outputAnalyser : session.micAnalyser;
  }, []);

  function start() {
    if (!sessionId || isActive) return;
    const session = new VoiceSession(dispatch);
    sessionRef.current = session;
    void session.start(sessionId);
  }

  function stop() {
    sessionRef.current?.stop();
  }

  return (
    <section aria-label="Voice" className="flex min-h-0 flex-1 flex-col">
      <div className="mx-auto w-full max-w-2xl px-4 pt-6">
        <div className="rounded-2xl border border-line bg-surface p-4">
          <div className="flex items-center gap-2">
            <span
              aria-hidden
              className={`size-2.5 rounded-full ${isActive ? "animate-pulse bg-ok" : state.status === "error" ? "bg-bad" : "bg-muted"}`}
            />
            <p className="text-sm font-medium" aria-live="polite">
              {STATUS_LABEL[state.status]}
            </p>
            <div className="ml-auto">
              {isActive ? (
                <button onClick={stop} className="h-10 rounded-xl bg-bad px-4 text-sm font-medium text-on-accent">
                  End call
                </button>
              ) : (
                <button
                  onClick={start}
                  disabled={!sessionId}
                  className="h-10 rounded-xl bg-accent px-4 text-sm font-medium text-on-accent disabled:opacity-40"
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
          <p className="mt-2 text-[11px] leading-snug text-muted">
            Voice can explain what we help with. To check your account or a refund, use the chat for now.
            {state.usage.reports > 0 &&
              ` Tokens this call: ${(state.usage.promptTokens + state.usage.responseTokens).toLocaleString()}.`}
          </p>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        <ol className="mx-auto flex max-w-2xl flex-col gap-3 px-4 py-6" aria-label="Voice transcript">
          {state.lines.length === 0 && (
            <li className="text-center text-xs text-muted">What you and the assistant say appears here.</li>
          )}
          {state.lines.map((line) => (
            <TranscriptLine key={line.id} line={line} />
          ))}
          <div ref={endRef} />
        </ol>
      </div>
    </section>
  );
}

function TranscriptLine({ line }: { line: VoiceLine }) {
  const isUser = line.role === "user";
  return (
    <li className={`flex ${isUser ? "justify-end" : ""}`}>
      <p
        className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm ${
          isUser ? "rounded-br-sm bg-accent text-on-accent" : "rounded-bl-sm bg-surface-2"
        } ${line.final ? "" : "opacity-70"}`}
      >
        {line.text}
        {line.interrupted && <span className="ml-1 text-xs text-muted">(interrupted)</span>}
      </p>
    </li>
  );
}
