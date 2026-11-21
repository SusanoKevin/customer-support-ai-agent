import { describe, expect, it } from "vitest";
import { audioChunkMessage, liveUrl, parseServerMessage, setupMessage } from "../protocol";

describe("Live wire protocol", () => {
  it("puts the ephemeral token in the query string of the constrained v1alpha endpoint", () => {
    const url = liveUrl("auth_tokens/abc+/=");
    expect(url).toContain("v1alpha.GenerativeService.BidiGenerateContentConstrained");
    expect(url).toContain("access_token=auth_tokens%2Fabc%2B%2F%3D");
  });

  it("sends only the model in setup, because the token locks everything else", () => {
    expect(JSON.parse(setupMessage("gemini-3.8-live"))).toEqual({ setup: { model: "models/gemini-3.8-live" } });
  });

  it("labels microphone chunks as 16 kHz PCM", () => {
    expect(JSON.parse(audioChunkMessage("AAA="))).toEqual({
      realtimeInput: { audio: { data: "AAA=", mimeType: "audio/pcm;rate=16000" } },
    });
  });

  it("parses setupComplete as ready", () => {
    expect(parseServerMessage('{"setupComplete":{}}')).toEqual([{ type: "ready" }]);
  });

  it("parses audio, transcripts and turn end from one message in order", () => {
    const raw = JSON.stringify({
      serverContent: {
        inputTranscription: { text: "Hi there" },
        modelTurn: { parts: [{ inlineData: { mimeType: "audio/pcm;rate=24000", data: "QUJD" } }, { text: "thinking" }] },
        outputTranscription: { text: "Hello" },
        turnComplete: true,
      },
    });
    expect(parseServerMessage(raw)).toEqual([
      { type: "input_transcript", text: "Hi there" },
      { type: "audio", data: "QUJD", sampleRate: 24000 },
      { type: "output_transcript", text: "Hello" },
      { type: "turn_complete" },
    ]);
  });

  it("reports barge-in as interrupted", () => {
    expect(parseServerMessage('{"serverContent":{"interrupted":true}}')).toEqual([{ type: "interrupted" }]);
  });

  it("reads usage metadata, defaulting missing counts to zero", () => {
    const raw = '{"usageMetadata":{"promptTokenCount":557,"responseTokenCount":72,"thoughtsTokenCount":54}}';
    expect(parseServerMessage(raw)).toEqual([{ type: "usage", promptTokens: 557, responseTokens: 72, thoughtsTokens: 54 }]);
    expect(parseServerMessage('{"usageMetadata":{}}')).toEqual([{ type: "usage", promptTokens: 0, responseTokens: 0, thoughtsTokens: 0 }]);
  });

  it("passes on a goAway warning", () => {
    expect(parseServerMessage('{"goAway":{"timeLeft":"10s"}}')).toEqual([{ type: "go_away", timeLeft: "10s" }]);
  });

  it("ignores messages it does not use and survives bad JSON", () => {
    expect(parseServerMessage('{"sessionResumptionUpdate":{}}')).toEqual([]);
    expect(parseServerMessage("not json")).toEqual([{ type: "protocol_error" }]);
  });

  it("defaults the audio rate to 24 kHz when the mime type has none", () => {
    const raw = '{"serverContent":{"modelTurn":{"parts":[{"inlineData":{"mimeType":"audio/pcm","data":"QQ=="}}]}}}';
    expect(parseServerMessage(raw)).toEqual([{ type: "audio", data: "QQ==", sampleRate: 24000 }]);
  });
});
