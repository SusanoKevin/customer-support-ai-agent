import { describe, expect, it } from "vitest";
import { initialVoice, voiceReducer, type VoiceAction, type VoiceState } from "../voiceState";

const run = (actions: VoiceAction[], from: VoiceState = initialVoice()) => actions.reduce(voiceReducer, from);

describe("voice reducer", () => {
  it("moves from connecting to listening when the session is ready", () => {
    const s = run([{ type: "connecting" }, { type: "live", event: { type: "ready" } }]);
    expect(s.status).toBe("listening");
  });

  it("joins transcript fragments into one line per speaker turn", () => {
    const s = run([
      { type: "live", event: { type: "ready" } },
      { type: "live", event: { type: "input_transcript", text: "What is" } },
      { type: "live", event: { type: "input_transcript", text: " your refund policy?" } },
      { type: "live", event: { type: "output_transcript", text: "The chat panel" } },
      { type: "live", event: { type: "output_transcript", text: " can check that." } },
      { type: "live", event: { type: "turn_complete" } },
    ]);
    expect(s.lines.map((l) => [l.role, l.text, l.final])).toEqual([
      ["user", "What is your refund policy?", true],
      ["agent", "The chat panel can check that.", true],
    ]);
  });

  it("starts a new user line after the agent finished", () => {
    const s = run([
      { type: "live", event: { type: "input_transcript", text: "Hi" } },
      { type: "live", event: { type: "output_transcript", text: "Hello" } },
      { type: "live", event: { type: "turn_complete" } },
      { type: "live", event: { type: "input_transcript", text: "Thanks" } },
    ]);
    expect(s.lines.map((l) => l.text)).toEqual(["Hi", "Hello", "Thanks"]);
  });

  it("shows speaking while audio plays and listening once playback drains", () => {
    const speaking = run([{ type: "live", event: { type: "ready" } }, { type: "live", event: { type: "audio", data: "", sampleRate: 24000 } }]);
    expect(speaking.status).toBe("speaking");
    expect(voiceReducer(speaking, { type: "playback_idle" }).status).toBe("listening");
  });

  it("marks the agent line as interrupted on barge-in and returns to listening", () => {
    const s = run([
      { type: "live", event: { type: "ready" } },
      { type: "live", event: { type: "output_transcript", text: "Our policy says" } },
      { type: "live", event: { type: "audio", data: "", sampleRate: 24000 } },
      { type: "live", event: { type: "interrupted" } },
    ]);
    expect(s.status).toBe("listening");
    expect(s.lines.at(-1)).toMatchObject({ role: "agent", interrupted: true, final: true });
  });

  it("adds usage across turns", () => {
    const usage = (p: number, r: number, t: number): VoiceAction => ({
      type: "live", event: { type: "usage", promptTokens: p, responseTokens: r, thoughtsTokens: t },
    });
    const s = run([usage(100, 20, 5), usage(300, 40, 0)]);
    expect(s.usage).toEqual({ promptTokens: 400, responseTokens: 60, thoughtsTokens: 5, reports: 2 });
  });

  it("keeps the transcript and records the error when the session fails", () => {
    const s = run([
      { type: "live", event: { type: "input_transcript", text: "Hi" } },
      { type: "failed", message: "Microphone blocked", retryable: false },
    ]);
    expect(s.status).toBe("error");
    expect(s.error).toEqual({ message: "Microphone blocked", retryable: false });
    expect(s.lines).toHaveLength(1);
  });

  it("clears an old error when reconnecting, keeping the transcript", () => {
    const s = run([
      { type: "live", event: { type: "input_transcript", text: "Hi" } },
      { type: "failed", message: "x", retryable: true },
      { type: "connecting" },
    ]);
    expect(s.error).toBeNull();
    expect(s.lines).toHaveLength(1);
  });

  it("warns before the server closes the session", () => {
    const s = run([{ type: "live", event: { type: "go_away", timeLeft: "10s" } }]);
    expect(s.notice).toContain("10s");
  });

  it("ends cleanly and finalises any open line", () => {
    const s = run([{ type: "live", event: { type: "input_transcript", text: "Bye" } }, { type: "ended" }]);
    expect(s.status).toBe("ended");
    expect(s.lines[0].final).toBe(true);
  });

  it("does not mutate the previous state", () => {
    const before = initialVoice();
    voiceReducer(before, { type: "live", event: { type: "input_transcript", text: "Hi" } });
    expect(before.lines).toHaveLength(0);
  });

  it("ignores protocol errors without dropping the session", () => {
    const s = run([{ type: "live", event: { type: "ready" } }, { type: "live", event: { type: "protocol_error" } }]);
    expect(s.status).toBe("listening");
  });
});
