// Voice panel state as a pure reducer, like lib/conversation.ts. VoiceSession dispatches; components only render.
import type { LiveEvent } from "./protocol";

export type VoiceStatus = "idle" | "connecting" | "listening" | "checking" | "speaking" | "ended" | "error";

export interface VoiceLine {
  id: string;
  role: "user" | "agent";
  text: string;
  final: boolean;
  interrupted: boolean;
}

export interface VoiceUsage {
  promptTokens: number;
  responseTokens: number;
  thoughtsTokens: number;
  reports: number;
}

export interface VoiceState {
  status: VoiceStatus;
  lines: readonly VoiceLine[];
  usage: VoiceUsage;
  error: { message: string; retryable: boolean } | null;
  notice: string | null;
}

export type VoiceAction =
  | { type: "connecting" }
  | { type: "live"; event: LiveEvent }
  | { type: "playback_idle" }
  | { type: "failed"; message: string; retryable: boolean }
  | { type: "ended" };

export function initialVoice(): VoiceState {
  return {
    status: "idle",
    lines: [],
    usage: { promptTokens: 0, responseTokens: 0, thoughtsTokens: 0, reports: 0 },
    error: null,
    notice: null,
  };
}

let nextId = 0;

function finalizeAll(lines: readonly VoiceLine[]): readonly VoiceLine[] {
  return lines.some((l) => !l.final) ? lines.map((l) => (l.final ? l : { ...l, final: true })) : lines;
}

/** Append to the open line of this speaker, or close the other speaker's line and open a new one. */
function appendText(lines: readonly VoiceLine[], role: VoiceLine["role"], text: string): readonly VoiceLine[] {
  const last = lines.at(-1);
  if (last && last.role === role && !last.final) {
    return [...lines.slice(0, -1), { ...last, text: last.text + text }];
  }
  return [...finalizeAll(lines), { id: `v${nextId++}`, role, text, final: false, interrupted: false }];
}

function markInterrupted(lines: readonly VoiceLine[]): readonly VoiceLine[] {
  const last = lines.at(-1);
  if (!last || last.role !== "agent" || last.final) return lines;
  return [...lines.slice(0, -1), { ...last, final: true, interrupted: true }];
}

function applyLive(state: VoiceState, event: LiveEvent): VoiceState {
  switch (event.type) {
    case "ready":
      return { ...state, status: "listening" };
    case "audio":
      return state.status === "speaking" ? state : { ...state, status: "speaking" };
    case "input_transcript":
      return { ...state, lines: appendText(state.lines, "user", event.text) };
    case "output_transcript":
      return { ...state, lines: appendText(state.lines, "agent", event.text) };
    case "interrupted":
      return { ...state, status: "listening", lines: markInterrupted(state.lines) };
    case "turn_complete":
      return { ...state, lines: finalizeAll(state.lines) };
    case "usage": {
      const u = state.usage;
      return {
        ...state,
        usage: {
          promptTokens: u.promptTokens + event.promptTokens,
          responseTokens: u.responseTokens + event.responseTokens,
          thoughtsTokens: u.thoughtsTokens + event.thoughtsTokens,
          reports: u.reports + 1,
        },
      };
    }
    case "tool_call":
      return { ...state, status: "checking" };
    case "tool_cancelled":
      return state; // the agent turn still finishes and shows in the chat transcript
    case "go_away":
      return { ...state, notice: `The voice session will close in ${event.timeLeft}.` };
    case "protocol_error":
      return state; // one unreadable frame is not worth ending the call; VoiceSession logs it
  }
}

export function voiceReducer(state: VoiceState, action: VoiceAction): VoiceState {
  switch (action.type) {
    case "connecting":
      return { ...state, status: "connecting", error: null, notice: null };
    case "live":
      return applyLive(state, action.event);
    case "playback_idle":
      return state.status === "speaking" ? { ...state, status: "listening" } : state;
    case "failed":
      return { ...state, status: "error", error: { message: action.message, retryable: action.retryable }, lines: finalizeAll(state.lines) };
    case "ended":
      return { ...state, status: "ended", lines: finalizeAll(state.lines) };
  }
}
