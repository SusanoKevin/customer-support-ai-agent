import type { AgentEvent } from "./events";
import { SseParser } from "./sse";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

/** Rate limits and server errors are worth retrying; a 4xx validation error is not. */
function isRetryableStatus(status: number): boolean {
  return status === 429 || status >= 500;
}

export class ChatRequestError extends Error {
  constructor(message: string, readonly retryable: boolean) {
    super(message);
  }
}

/** Streams one agent turn. Yields events as they arrive; throws ChatRequestError if the request fails. */
export async function* streamChat(sessionId: string, message: string, signal?: AbortSignal): AsyncGenerator<AgentEvent> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "text/event-stream" },
      body: JSON.stringify({ session_id: sessionId, message }),
      signal,
    });
  } catch {
    throw new ChatRequestError("Could not reach the support service. Check your connection and try again.", true);
  }
  if (!response.ok) throw await errorFrom(response, `The support service returned ${response.status}.`);
  if (!response.body) throw new ChatRequestError("The support service sent an empty reply.", true);
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  const parser = new SseParser();
  while (true) {
    const { value, done } = await reader.read();
    if (done) return;
    yield* parser.push(value);
  }
}

export interface VoiceToken {
  token: string;
  model: string;
  expiresAt: string;
}

/** Uses the server's `detail.message` (rate limits, voice errors) when there is one. */
async function errorFrom(response: Response, fallback: string): Promise<ChatRequestError> {
  const fallbackRetryable = isRetryableStatus(response.status);
  try {
    const body = (await response.json()) as { detail?: { message?: unknown; retryable?: unknown } };
    const { message, retryable } = body.detail ?? {};
    if (typeof message === "string") {
      return new ChatRequestError(message, typeof retryable === "boolean" ? retryable : fallbackRetryable);
    }
  } catch {
    // Not JSON: fall through to the generic message.
  }
  return new ChatRequestError(fallback, fallbackRetryable);
}

/** Asks the backend for a single-use Live token. The real API key never reaches the browser. */
export async function fetchVoiceToken(sessionId: string, signal?: AbortSignal): Promise<VoiceToken> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/voice/token`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ session_id: sessionId }),
      signal,
    });
  } catch {
    throw new ChatRequestError("Could not reach the support service. Check your connection and try again.", true);
  }
  if (!response.ok) throw await errorFrom(response, `Voice couldn't start (error ${response.status}).`);
  const body = (await response.json()) as { token?: unknown; model?: unknown; expires_at?: unknown };
  if (typeof body.token !== "string" || typeof body.model !== "string") {
    throw new ChatRequestError("Voice couldn't start. Please try again.", true);
  }
  return { token: body.token, model: body.model, expiresAt: String(body.expires_at ?? "") };
}
