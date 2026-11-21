// Gemini Live wire format, as used with an ephemeral token. Pure functions only, so they are unit tested.
// The token locks model, prompt and transcription on the server (backend/app/voice.py), so setup sends only the model.
// Ephemeral tokens work only on v1alpha's constrained endpoint; browsers cannot set an Authorization
// header on a WebSocket, so the token goes in the query string.

const LIVE_ENDPOINT =
  "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContentConstrained";

export const INPUT_SAMPLE_RATE = 16000; // what Live expects from the microphone
const DEFAULT_OUTPUT_RATE = 24000; // what Live sends back

export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
}

export type LiveEvent =
  | { type: "ready" }
  | { type: "audio"; data: string; sampleRate: number }
  | { type: "input_transcript"; text: string }
  | { type: "output_transcript"; text: string }
  | { type: "interrupted" }
  | { type: "turn_complete" }
  | { type: "usage"; promptTokens: number; responseTokens: number; thoughtsTokens: number }
  | { type: "tool_call"; calls: ToolCall[] }
  | { type: "tool_cancelled"; ids: string[] }
  | { type: "go_away"; timeLeft: string }
  | { type: "protocol_error" };

export function liveUrl(token: string): string {
  return `${LIVE_ENDPOINT}?access_token=${encodeURIComponent(token)}`;
}

export function setupMessage(model: string): string {
  return JSON.stringify({ setup: { model: `models/${model}` } });
}

export function audioChunkMessage(base64Pcm: string): string {
  return JSON.stringify({ realtimeInput: { audio: { data: base64Pcm, mimeType: `audio/pcm;rate=${INPUT_SAMPLE_RATE}` } } });
}

export function toolResponseMessage(id: string, name: string, response: Record<string, unknown>): string {
  return JSON.stringify({ toolResponse: { functionResponses: [{ id, name, response }] } });
}

interface Part {
  inlineData?: { mimeType?: string; data?: string };
}

interface ServerMessage {
  setupComplete?: object;
  serverContent?: {
    inputTranscription?: { text?: string };
    modelTurn?: { parts?: Part[] };
    outputTranscription?: { text?: string };
    interrupted?: boolean;
    turnComplete?: boolean;
  };
  usageMetadata?: { promptTokenCount?: number; responseTokenCount?: number; thoughtsTokenCount?: number };
  goAway?: { timeLeft?: string };
  toolCall?: { functionCalls?: { id?: string; name?: string; args?: Record<string, unknown> }[] };
  toolCallCancellation?: { ids?: string[] };
}

function toolCalls(raw: NonNullable<ServerMessage["toolCall"]>): ToolCall[] {
  return (raw.functionCalls ?? [])
    .filter((c) => typeof c.id === "string" && typeof c.name === "string")
    .map((c) => ({ id: c.id!, name: c.name!, args: c.args ?? {} }));
}

function sampleRateOf(mimeType: string | undefined): number {
  const match = /rate=(\d+)/.exec(mimeType ?? "");
  return match ? Number(match[1]) : DEFAULT_OUTPUT_RATE;
}

function contentEvents(content: NonNullable<ServerMessage["serverContent"]>): LiveEvent[] {
  const events: LiveEvent[] = [];
  if (content.inputTranscription?.text) events.push({ type: "input_transcript", text: content.inputTranscription.text });
  for (const part of content.modelTurn?.parts ?? []) {
    const inline = part.inlineData;
    if (inline?.data && inline.mimeType?.startsWith("audio/")) {
      events.push({ type: "audio", data: inline.data, sampleRate: sampleRateOf(inline.mimeType) });
    }
  }
  if (content.outputTranscription?.text) events.push({ type: "output_transcript", text: content.outputTranscription.text });
  if (content.interrupted) events.push({ type: "interrupted" });
  if (content.turnComplete) events.push({ type: "turn_complete" });
  return events;
}

/** One server frame can carry several things (audio + transcript + turn end); order is preserved. */
export function parseServerMessage(raw: string): LiveEvent[] {
  let msg: ServerMessage;
  try {
    msg = JSON.parse(raw) as ServerMessage;
  } catch {
    return [{ type: "protocol_error" }];
  }
  const events: LiveEvent[] = [];
  if (msg.setupComplete) events.push({ type: "ready" });
  if (msg.serverContent) events.push(...contentEvents(msg.serverContent));
  if (msg.usageMetadata) {
    const u = msg.usageMetadata;
    events.push({
      type: "usage",
      promptTokens: u.promptTokenCount ?? 0,
      responseTokens: u.responseTokenCount ?? 0,
      thoughtsTokens: u.thoughtsTokenCount ?? 0,
    });
  }
  if (msg.toolCall) events.push({ type: "tool_call", calls: toolCalls(msg.toolCall) });
  if (msg.toolCallCancellation) events.push({ type: "tool_cancelled", ids: msg.toolCallCancellation.ids ?? [] });
  if (msg.goAway) events.push({ type: "go_away", timeLeft: msg.goAway.timeLeft ?? "soon" });
  return events;
}
