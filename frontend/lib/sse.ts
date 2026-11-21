// Parses `text/event-stream` frames from a POST response body into typed AgentEvents.
// fetch + ReadableStream is used instead of EventSource because EventSource cannot send a body.
import type { AgentEvent } from "./events";

const KNOWN_EVENTS: ReadonlySet<string> = new Set(["status", "token", "tool", "escalation", "trace", "error", "done"]);
const FRAME_BREAK = /\r?\n\r?\n/;

function parseFrame(frame: string): AgentEvent | null {
  let name = "";
  const dataLines: string[] = [];
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!KNOWN_EVENTS.has(name) || dataLines.length === 0) return null;
  try {
    return { event: name, data: JSON.parse(dataLines.join("\n")) } as AgentEvent;
  } catch {
    return null;
  }
}

export class SseParser {
  private buffer = "";

  push(chunk: string): AgentEvent[] {
    const parts = (this.buffer + chunk).split(FRAME_BREAK);
    this.buffer = parts.pop() ?? "";
    return parts.map(parseFrame).filter((e): e is AgentEvent => e !== null);
  }
}
