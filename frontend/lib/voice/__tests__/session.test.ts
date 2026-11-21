// Start/stop ordering only. Audio and WebSocket paths are verified in the browser (log D28).
import { afterEach, describe, expect, it, vi } from "vitest";
import { VoiceSession } from "../session";
import type { VoiceAction } from "../voiceState";

afterEach(() => vi.unstubAllGlobals());

function deferredMic() {
  const track = { stop: vi.fn() };
  let grant: () => void = () => {};
  const getUserMedia = () => new Promise((resolve) => (grant = () => resolve({ getTracks: () => [track] })));
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
  return { track, grant: () => grant() };
}

const tokenResponse = () => Response.json({ token: "auth_tokens/x", model: "gemini-3.8-live", expires_at: "t" });

function recorder() {
  const actions: VoiceAction[] = [];
  return { actions, session: new VoiceSession((a) => actions.push(a)) };
}

describe("VoiceSession start and stop", () => {
  it("releases the mic and mints no token when stopped during the permission prompt", async () => {
    const mic = deferredMic();
    const fetchMock = vi.fn().mockResolvedValue(tokenResponse());
    vi.stubGlobal("fetch", fetchMock);
    const { actions, session } = recorder();

    const starting = session.start("s-12345678");
    session.stop();
    mic.grant();
    await starting;

    expect(mic.track.stop).toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(actions.map((a) => a.type)).toEqual(["connecting", "ended"]);
  });

  it("aborts the token request and releases the mic when stopped while fetching the token", async () => {
    const mic = deferredMic();
    let signal: AbortSignal | undefined;
    vi.stubGlobal("fetch", vi.fn((_url: string, init: RequestInit) => {
      signal = init.signal ?? undefined;
      return new Promise((_, reject) => signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))));
    }));
    const { actions, session } = recorder();

    const starting = session.start("s-12345678");
    mic.grant();
    await vi.waitFor(() => expect(signal).toBeDefined());
    session.stop();
    await starting;

    expect(signal?.aborted).toBe(true);
    expect(mic.track.stop).toHaveBeenCalled();
    expect(actions.map((a) => a.type)).toEqual(["connecting", "ended"]); // no "failed" after the user ended it
  });

  it("explains a blocked microphone", async () => {
    vi.stubGlobal("navigator", {
      mediaDevices: { getUserMedia: () => Promise.reject(new DOMException("denied", "NotAllowedError")) },
    });
    const { actions, session } = recorder();

    await session.start("s-12345678");

    expect(actions.at(-1)).toMatchObject({ type: "failed", retryable: true });
    expect(JSON.stringify(actions.at(-1))).toContain("Microphone access is blocked");
  });
});
