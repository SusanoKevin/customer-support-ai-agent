"use client";
import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { ChatRequestError, streamChat } from "@/lib/api";
import { applyEvent, failTurn, initialConversation, sessionTotals, startTurn, type Channel, type Conversation } from "@/lib/conversation";
import { getServerSessionId, getSessionId, resetSessionId, subscribeSessionId } from "@/lib/session";
import { Composer } from "./chat/Composer";
import { MessageBubble } from "./chat/MessageBubble";
import { TraceDrawer } from "./observability/TraceDrawer";
import { useVoiceCall } from "./voice/useVoiceCall";
import { VoicePanel } from "./voice/VoicePanel";

type View = "chat" | "voice" | "trace";

const AGENT_BUSY = "The support agent is still working on the last request. Ask the customer to wait a moment.";
const AGENT_FAILED = "The support agent couldn't be reached just now. Ask the customer to try again in a moment.";

const SUGGESTIONS = [
  "What is your refund policy for Pro plans?",
  "I want a $30 refund on invoice in_m1. maya@example.com, last 4 is 4242",
  "I want an $80 refund on invoice in_m1. maya@example.com, last 4 is 4242",
  "Can I talk to a person?",
];

/** Floating support chat: a launcher bubble that opens a panel with chat, live voice and the trace. */
export function SupportWidget() {
  const [conversation, setConversation] = useState<Conversation>(initialConversation);
  const sessionId = useSyncExternalStore(subscribeSessionId, getSessionId, getServerSessionId);
  const [isOpen, setIsOpen] = useState(false);
  const [view, setView] = useState<View>("chat");
  const abortRef = useRef<AbortController | null>(null);
  const busyRef = useRef(false);
  const endRef = useRef<HTMLDivElement>(null);
  const call = useVoiceCall(sessionId, (message) => runTurn(message, "voice"));

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [conversation.messages, view, isOpen]);

  /** One agent turn, from the chat box or a voice tool call. Resolves with the reply text; never throws. */
  async function runTurn(text: string, via: Channel): Promise<string> {
    if (!sessionId) return AGENT_FAILED;
    if (busyRef.current) return AGENT_BUSY;
    busyRef.current = true;
    const controller = new AbortController();
    abortRef.current = controller;
    setConversation((c) => startTurn(c, text, via));
    let reply = "";
    try {
      for await (const event of streamChat(sessionId, text, controller.signal)) {
        if (event.event === "token") reply += event.data.text;
        setConversation((c) => applyEvent(c, event));
      }
    } catch (error: unknown) {
      if (controller.signal.aborted) return AGENT_FAILED;
      const retryable = error instanceof ChatRequestError ? error.retryable : true;
      const message = error instanceof Error ? error.message : "Something went wrong. Please try again.";
      setConversation((c) => failTurn(c, { code: "network", message, retryable }));
      return error instanceof ChatRequestError ? message : AGENT_FAILED;
    } finally {
      busyRef.current = false;
    }
    // A stream that closed without `done` must not leave the input locked.
    setConversation((c) => (c.busy ? failTurn(c, { code: "incomplete", message: "The reply was cut off.", retryable: true }) : c));
    return reply || AGENT_FAILED;
  }

  function send(text: string) {
    if (!conversation.busy) void runTurn(text, "chat");
  }

  function startVoice() {
    setView("voice");
    call.start(); // still inside the mic click
  }

  function resetSession() {
    call.stop();
    abortRef.current?.abort();
    resetSessionId();
    setConversation(initialConversation());
    setView("chat");
  }

  const lastIndex = conversation.messages.length - 1;
  const lastPrompt = conversation.lastPrompt;
  const retry = lastPrompt ? () => send(lastPrompt) : undefined;
  const title = view === "voice" ? "Voice call" : "Support Agent";

  return (
    <>
      {isOpen && (
        <div
          role="dialog"
          aria-label="Support chat"
          className="fixed inset-0 z-50 flex flex-col overflow-hidden bg-surface text-fg shadow-2xl sm:inset-auto sm:right-6 sm:bottom-24 sm:h-[min(680px,calc(100dvh-8rem))] sm:w-[400px] sm:rounded-2xl sm:border sm:border-line"
        >
          <header className="flex items-center gap-2 border-b border-line px-3 py-2.5">
            {view !== "chat" ? (
              <IconButton label="Back to chat" onClick={() => setView("chat")}>
                <path d="M15 6l-6 6 6 6" />
              </IconButton>
            ) : (
              <div className="flex size-8 items-center justify-center rounded-lg bg-accent text-sm font-bold text-on-accent">S</div>
            )}
            <div className="min-w-0">
              <h2 className="text-sm font-semibold">{title}</h2>
              <p className="truncate text-[11px] text-muted">Billing, refunds and plans. A person can take over.</p>
            </div>
            <div className="ml-auto flex shrink-0 gap-1">
              <IconButton label="Show trace" isPressed={view === "trace"} onClick={() => setView(view === "trace" ? "chat" : "trace")}>
                <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
              </IconButton>
              <IconButton label="New session" onClick={resetSession}>
                <path d="M4 12a8 8 0 1 0 2.3-5.6M4 4v4h4" />
              </IconButton>
              <IconButton label="Close chat" onClick={() => setIsOpen(false)}>
                <path d="M6 6l12 12M18 6L6 18" />
              </IconButton>
            </div>
          </header>

          {view === "trace" && (
            <div className="min-h-0 flex-1">
              <TraceDrawer turns={conversation.turns} session={sessionTotals(conversation)} sessionId={sessionId} />
            </div>
          )}

          {view === "voice" && <VoicePanel call={call} canStart={Boolean(sessionId)} />}

          {view === "chat" && (
            <>
              <div className="min-h-0 flex-1 overflow-y-auto">
                <div className="flex flex-col gap-4 px-3 py-4">
                  {conversation.messages.length === 0 && <EmptyState onPick={send} isDisabled={!sessionId} />}
                  {conversation.messages.map((m, i) => (
                    <MessageBubble
                      key={m.id}
                      message={m}
                      live={conversation.busy && i === lastIndex}
                      onRetry={i === lastIndex && !conversation.busy ? retry : undefined}
                    />
                  ))}
                  <div ref={endRef} />
                </div>
              </div>
              {call.isActive && (
                <button onClick={() => setView("voice")} className="border-t border-line bg-surface-2 px-3 py-1.5 text-left text-xs text-ok">
                  Voice call in progress. Tap to return.
                </button>
              )}
              <Composer disabled={conversation.busy || !sessionId} onSend={send} onMic={startVoice} />
            </>
          )}
        </div>
      )}

      <button
        onClick={() => setIsOpen((o) => !o)}
        aria-label={isOpen ? "Close support chat" : "Open support chat"}
        aria-expanded={isOpen}
        className={`fixed right-6 bottom-6 z-50 size-14 items-center justify-center rounded-full bg-accent text-on-accent shadow-lg transition hover:scale-105 ${isOpen ? "hidden sm:flex" : "flex"}`}
      >
        {call.isActive && !isOpen && <span aria-hidden className="absolute top-0 right-0 size-3.5 animate-pulse rounded-full border-2 border-bg bg-ok" />}
        <svg aria-hidden viewBox="0 0 24 24" className="size-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          {isOpen ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z" />}
        </svg>
      </button>
    </>
  );
}

interface IconButtonProps {
  label: string;
  onClick: () => void;
  isPressed?: boolean;
  children: ReactNode;
}

function IconButton({ label, onClick, isPressed, children }: IconButtonProps) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      title={label}
      aria-pressed={isPressed}
      className={`flex size-8 items-center justify-center rounded-lg transition hover:bg-surface-2 ${isPressed ? "bg-surface-2 text-accent" : "text-muted"}`}
    >
      <svg aria-hidden viewBox="0 0 24 24" className="size-4.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        {children}
      </svg>
    </button>
  );
}

function EmptyState({ onPick, isDisabled }: { onPick: (text: string) => void; isDisabled: boolean }) {
  return (
    <div className="py-4 text-center">
      <h3 className="text-base font-semibold">How can we help?</h3>
      <p className="mt-1 text-xs text-muted">Type a question, tap the mic to talk, or try one of these.</p>
      <div className="mt-4 grid gap-2 text-left">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            disabled={isDisabled}
            onClick={() => onPick(s)}
            className="rounded-xl border border-line bg-surface px-3 py-2 text-xs hover:border-accent disabled:opacity-50"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
