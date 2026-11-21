import { describe, expect, it } from "vitest";
import { base64ToBytes, bytesToBase64, downsample, floatToPcm16, pcm16ToFloat } from "../pcm";

describe("PCM helpers", () => {
  it("averages samples when downsampling 48 kHz to 16 kHz", () => {
    const input = Float32Array.from([0, 0.3, 0.6, 1, 1, 1]);
    expect(Array.from(downsample(input, 48000, 16000)).map((v) => +v.toFixed(2))).toEqual([0.3, 1]);
  });

  it("returns the input unchanged when rates match", () => {
    const input = Float32Array.from([0.1, 0.2]);
    expect(downsample(input, 16000, 16000)).toBe(input);
  });

  it("refuses to upsample", () => {
    expect(() => downsample(new Float32Array(4), 8000, 16000)).toThrow();
  });

  it("clips and scales floats to signed 16-bit", () => {
    expect(Array.from(floatToPcm16(Float32Array.from([-2, -1, 0, 0.5, 1, 2])))).toEqual([-32768, -32768, 0, 16383, 32767, 32767]);
  });

  it("round-trips 16-bit samples to floats", () => {
    const back = pcm16ToFloat(Int16Array.from([-32768, 0, 16384]));
    expect(Array.from(back)).toEqual([-1, 0, 0.5]);
  });

  it("round-trips bytes through base64, including large buffers", () => {
    const bytes = Uint8Array.from({ length: 70000 }, (_, i) => i % 256);
    const encoded = bytesToBase64(bytes);
    expect(encoded.startsWith("AAECAw")).toBe(true);
    expect(base64ToBytes(encoded)).toEqual(bytes);
  });
});
