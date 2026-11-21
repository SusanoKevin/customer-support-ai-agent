"use client";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { ChatRequestError, streamChat } from "@/lib/api";
import { applyEvent, failTurn, initialConversation, sessionTotals, startTurn, type Conversation } from "@/lib/conversation";
import { getServerSessionId, getSessionId, resetSessionId, subscribeSessionId } from "@/lib/session";
import { Composer } from "./chat/Composer";
import { MessageBubble } from "./chat/MessageBubble";
import { TraceDrawer } from "./observability/TraceDrawer";

const SUGGESTIONS = [
  "What is your refund policy for Pro plans?",
  "I want a $30 refund on invoice in_m1. maya@example.com, last 4 is 4242",
  "I want an $80 refund on invoice in_m1. maya@example.com, last 4 is 4242",
  "Can I talk to a person?",
];

export function SupportConsole() {
  const [conversation, setConversation] = useState<Conversation>(initialConversation);
  const sessionId = useSyncExternalStore(subscribeSessionId, getSessionId, getServerSessionId);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [conversation.messages]);

  async function send(text: string) {
    if (!sessionId || conversation.busy) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setConversation((c) => startTurn(c, text));
    try {
      for await (const event of streamChat(sessionId, text, controller.signal)) {
        setConversation((c) => applyEvent(c, event));
      }
    } catch (error: unknown) {
      if (controller.signal.aborted) return;
      const retryable = error instanceof ChatRequestError ? error.retryable : true;
      const message = error instanceof Error ? error.message : "Something went wrong. Please try again.";
      setConversation((c) => failTurn(c, { code: "network", message, retryable }));
      return;
    }
    // A stream that closed without `done` must not leave the input locked.
    setConversation((c) => (c.busy ? failTurn(c, { code: "incomplete", message: "The reply was cut off.", retryable: true }) : c));
  }

  function resetSession() {
    abortRef.current?.abort();
    resetSessionId();
    setConversation(initialConversation());
  }

  const lastIndex = conversation.messages.length - 1;
  const lastPrompt = conversation.lastPrompt;
  const retry = lastPrompt ? () => send(lastPrompt) : undefined;

  return (
    <div className="flex h-dvh flex-col">
      <header className="flex items-center gap-3 border-b border-line bg-surface px-4 py-3">
        <div className="flex size-8 items-center justify-center rounded-lg bg-accent text-sm font-bold text-on-accent">S</div>
        <div className="min-w-0">
          <h1 className="text-sm font-semibold">Support Assistant</h1>
          <p className="truncate text-xs text-muted">Billing, refunds and plans. A person can take over at any time.</p>
        </div>
        <div className="ml-auto flex shrink-0 gap-2">
          <button onClick={resetSession} className="rounded-lg border border-line px-3 py-1.5 text-xs hover:bg-surface-2">
            New session
          </button>
          <button
            onClick={() => setIsDrawerOpen((o) => !o)}
            aria-expanded={isDrawerOpen}
            aria-controls="trace-drawer"
            className="rounded-lg border border-line px-3 py-1.5 text-xs hover:bg-surface-2 lg:hidden"
          >
            Trace
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <main className="flex min-w-0 flex-1 flex-col">
          <div className="flex-1 overflow-y-auto">
            <div className="mx-auto flex max-w-2xl flex-col gap-4 px-4 py-6">
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
          <div className="mx-auto w-full max-w-2xl">
            <Composer disabled={conversation.busy || !sessionId} onSend={send} />
          </div>
        </main>

        <aside
          id="trace-drawer"
          className={`${isDrawerOpen ? "fixed inset-x-0 bottom-0 top-14 z-10" : "hidden"} border-l border-line bg-surface lg:static lg:block lg:w-96`}
        >
          <TraceDrawer turns={conversation.turns} session={sessionTotals(conversation)} sessionId={sessionId} />
        </aside>
      </div>
    </div>
  );
}

function EmptyState({ onPick, isDisabled }: { onPick: (text: string) => void; isDisabled: boolean }) {
  return (
    <div className="py-8 text-center">
      <h2 className="text-lg font-semibold">How can we help?</h2>
      <p className="mt-1 text-sm text-muted">Try one of these, or ask your own question.</p>
      <div className="mt-5 grid gap-2 text-left sm:grid-cols-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            disabled={isDisabled}
            onClick={() => onPick(s)}
            className="rounded-xl border border-line bg-surface px-3 py-2.5 text-xs hover:border-accent disabled:opacity-50"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
