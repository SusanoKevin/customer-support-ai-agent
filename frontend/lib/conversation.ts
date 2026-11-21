// Pure state for one support conversation. Every function returns a new object; nothing is mutated.
import type { AgentEvent, Priority, StepState } from "./events";

export interface Step { step: string; label: string; state: StepState }
export interface ToolCall { name: string; input: Record<string, unknown>; output: Record<string, unknown> | null; ok: boolean }
export interface Escalation { reason: string; ticket_id: string | null; priority: Priority | null }
export interface TurnError { code: string; message: string; retryable: boolean }

export interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  steps: Step[];
  tools: ToolCall[];
  escalation: Escalation | null;
  error: TurnError | null;
}

export interface TraceRow { step: string; latencyMs: number; model: string | null; tokensIn: number; tokensOut: number; costUsd: number }
export interface Turn { id: string; prompt: string; rows: TraceRow[] }

export interface Conversation {
  messages: Message[];
  turns: Turn[];
  busy: boolean;
  lastPrompt: string | null;
}

export interface Totals { latencyMs: number; tokensIn: number; tokensOut: number; costUsd: number }

export function initialConversation(): Conversation {
  return { messages: [], turns: [], busy: false, lastPrompt: null };
}

function message(id: string, role: Message["role"], text: string): Message {
  return { id, role, text, steps: [], tools: [], escalation: null, error: null };
}

export function startTurn(state: Conversation, prompt: string): Conversation {
  const n = state.turns.length + 1;
  return {
    messages: [...state.messages, message(`u${n}`, "user", prompt), message(`a${n}`, "assistant", "")],
    turns: [...state.turns, { id: `t${n}`, prompt, rows: [] }],
    busy: true,
    lastPrompt: prompt,
  };
}

function updateReply(state: Conversation, change: (m: Message) => Message): Conversation {
  const last = state.messages.length - 1;
  if (last < 0 || state.messages[last].role !== "assistant") return state;
  return { ...state, messages: state.messages.map((m, i) => (i === last ? change(m) : m)) };
}

function updateTurn(state: Conversation, row: TraceRow): Conversation {
  const last = state.turns.length - 1;
  if (last < 0) return state;
  return { ...state, turns: state.turns.map((t, i) => (i === last ? { ...t, rows: [...t.rows, row] } : t)) };
}

function upsertStep(steps: Step[], next: Step): Step[] {
  const index = steps.findIndex((s) => s.step === next.step && s.state === "started");
  return index === -1 ? [...steps, next] : steps.map((s, i) => (i === index ? next : s));
}

export function applyEvent(state: Conversation, event: AgentEvent): Conversation {
  switch (event.event) {
    case "status":
      return updateReply(state, (m) => ({ ...m, steps: upsertStep(m.steps, event.data) }));
    case "token":
      return updateReply(state, (m) => ({ ...m, text: m.text + event.data.text }));
    case "tool":
      return updateReply(state, (m) => ({ ...m, tools: [...m.tools, event.data] }));
    case "escalation":
      return updateReply(state, (m) => ({ ...m, escalation: event.data }));
    case "error":
      return updateReply(state, (m) => ({ ...m, error: event.data }));
    case "trace": {
      const d = event.data;
      return updateTurn(state, {
        step: d.step, latencyMs: d.latency_ms, model: d.model, tokensIn: d.tokens_in, tokensOut: d.tokens_out, costUsd: d.cost_usd,
      });
    }
    case "done":
      return { ...state, busy: false };
  }
}

/** Ends a turn the stream did not finish, for example when the network drops. */
export function failTurn(state: Conversation, error: TurnError): Conversation {
  return { ...updateReply(state, (m) => ({ ...m, error })), busy: false };
}

export function totals(rows: TraceRow[]): Totals {
  return rows.reduce(
    (t, r) => ({ latencyMs: t.latencyMs + r.latencyMs, tokensIn: t.tokensIn + r.tokensIn, tokensOut: t.tokensOut + r.tokensOut, costUsd: t.costUsd + r.costUsd }),
    { latencyMs: 0, tokensIn: 0, tokensOut: 0, costUsd: 0 },
  );
}

export function sessionTotals(state: Conversation): Totals {
  return totals(state.turns.flatMap((t) => t.rows));
}
