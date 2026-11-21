import { afterEach, describe, expect, it, vi } from "vitest";
import { ChatRequestError, fetchVoiceToken, streamChat } from "../api";
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

  it("shows the server's wait message when chat is rate limited", async () => {
    const body = { detail: { message: "Too many messages. Please wait 12 seconds and try again.", retryable: true } };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(body, { status: 429 })));
    await expect(collect(streamChat("s-12345678", "hi"))).rejects.toMatchObject({
      message: "Too many messages. Please wait 12 seconds and try again.",
      retryable: true,
    });
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

describe("fetchVoiceToken", () => {
  it("posts the session id and returns the token and model", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      Response.json({ token: "auth_tokens/x", model: "gemini-3.8-live", expires_at: "t1", new_session_expires_at: "t0" }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const token = await fetchVoiceToken("s-12345678");

    expect(token).toEqual({ token: "auth_tokens/x", model: "gemini-3.8-live", expiresAt: "t1" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/api\/voice\/token$/);
    expect(JSON.parse(init.body)).toEqual({ session_id: "s-12345678" });
  });

  it("uses the server's message and retry flag on a 503", async () => {
    const body = { detail: { message: "Voice isn't available on this server.", retryable: false } };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(body, { status: 503 })));

    await expect(fetchVoiceToken("s-12345678")).rejects.toMatchObject({
      message: "Voice isn't available on this server.",
      retryable: false,
    });
  });

  it("falls back to a generic message when the error body is not JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("oops", { status: 500 })));
    const error = await fetchVoiceToken("s-12345678").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ChatRequestError);
    expect(error).toMatchObject({ retryable: true });
  });

  it("reports a network failure as retryable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(fetchVoiceToken("s-12345678")).rejects.toMatchObject({ retryable: true });
  });

  it("rejects a reply without a token", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ model: "m" })));
    await expect(fetchVoiceToken("s-12345678")).rejects.toMatchObject({ retryable: true });
  });
});
