import type { AgentEvent } from "./events";
import { SseParser } from "./sse";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

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
  if (!response.ok || !response.body) {
    const retryable = response.status === 429 || response.status >= 500;
    throw new ChatRequestError(`The support service returned ${response.status}.`, retryable);
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  const parser = new SseParser();
  while (true) {
    const { value, done } = await reader.read();
    if (done) return;
    yield* parser.push(value);
  }
}
