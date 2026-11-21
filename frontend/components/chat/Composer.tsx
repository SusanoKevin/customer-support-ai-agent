"use client";
import { useState, type FormEvent, type KeyboardEvent } from "react";

const MAX_LENGTH = 2000; // matches ChatRequest.message in backend/app/main.py

interface ComposerProps {
  disabled: boolean;
  onSend: (text: string) => void;
}

export function Composer({ disabled, onSend }: ComposerProps) {
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
        placeholder="Ask about billing, refunds or your plan..."
        className="max-h-40 min-h-11 flex-1 resize-none rounded-xl border border-line bg-surface-2 px-3 py-2.5 text-sm outline-none focus:border-accent"
      />
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
