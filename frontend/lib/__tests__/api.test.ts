import { afterEach, describe, expect, it, vi } from "vitest";
import { ChatRequestError, streamChat } from "../api";
import { failTurn, initialConversation, startTurn } from "../conversation";
import type { AgentEvent } from "../events";

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      chunks.forEach((c) => controller.enqueue(encoder.encode(c)));
      controller.close();
    },
  });
}

async function collect(gen: AsyncGenerator<AgentEvent>): Promise<AgentEvent[]> {
  const out: AgentEvent[] = [];
  for await (const e of gen) out.push(e);
  return out;
}

afterEach(() => vi.unstubAllGlobals());

describe("streamChat", () => {
  it("posts the session and message and yields events as chunks arrive", async () => {
    const body = streamOf([
      'event: token\r\ndata: {"text":"Hi"}\r\n\r\nevent: do',
      'ne\r\ndata: {"session_id":"s-12345678"}\r\n\r\n',
    ]);
    const fetchMock = vi.fn().mockResolvedValue(new Response(body, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const events = await collect(streamChat("s-12345678", "hello"));

    expect(events.map((e) => e.event)).toEqual(["token", "done"]);
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body)).toEqual({ session_id: "s-12345678", message: "hello" });
  });

  it("reports a network failure as retryable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(collect(streamChat("s-12345678", "hi"))).rejects.toMatchObject({ retryable: true });
  });

  it("treats 429 and 5xx as retryable and 422 as not", async () => {
    const cases: Array<[number, boolean]> = [[429, true], [503, true], [422, false]];
    for (const [status, retryable] of cases) {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("x", { status })));
      const error = await collect(streamChat("s-12345678", "hi")).catch((e: unknown) => e);
      expect(error).toBeInstanceOf(ChatRequestError);
      expect((error as ChatRequestError).retryable).toBe(retryable);
    }
  });
});

describe("failTurn", () => {
  it("unlocks the input and attaches the error to the reply", () => {
    const error = { code: "network", message: "Offline", retryable: true };
    const state = failTurn(startTurn(initialConversation(), "Hi"), error);
    expect(state.busy).toBe(false);
    expect(state.messages[1].error?.message).toBe("Offline");
  });
});
