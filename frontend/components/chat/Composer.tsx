"use client";
import { useState, type FormEvent, type KeyboardEvent } from "react";

const MAX_LENGTH = 2000; // matches ChatRequest.message in backend/app/main.py

interface ComposerProps {
  disabled: boolean;
  onSend: (text: string) => void;
  /** Starts a live voice call. Runs inside the click, which phones need to start audio. */
  onMic: () => void;
}

export function Composer({ disabled, onSend, onMic }: ComposerProps) {
  const [text, setText] = useState("");
  const trimmed = text.trim();

  function submit(e?: FormEvent) {
    e?.preventDefault();
    if (disabled || !trimmed) return;
    onSend(trimmed);
    setText("");
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) submit(e);
  }

  return (
    <form onSubmit={submit} className="flex items-end gap-2 border-t border-line bg-surface p-3">
      <label htmlFor="composer" className="sr-only">
        Message
      </label>
      <textarea
        id="composer"
        rows={1}
        value={text}
        maxLength={MAX_LENGTH}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Ask about billing or refunds..."
        className="max-h-40 min-h-11 flex-1 resize-none rounded-xl border border-line bg-surface-2 px-3 py-2.5 text-sm outline-none focus:border-accent"
      />
      <button
        type="button"
        onClick={onMic}
        disabled={disabled}
        aria-label="Start a voice call"
        title="Talk to the assistant"
        className="flex size-11 shrink-0 items-center justify-center rounded-xl border border-line text-muted transition hover:border-accent hover:text-accent disabled:opacity-40"
      >
        <svg aria-hidden viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <rect x="9" y="3" width="6" height="11" rx="3" />
          <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
        </svg>
      </button>
      <button
        type="submit"
        disabled={disabled || !trimmed}
        className="h-11 rounded-xl bg-accent px-4 text-sm font-medium text-on-accent transition disabled:opacity-40"
      >
        Send
      </button>
    </form>
  );
}
