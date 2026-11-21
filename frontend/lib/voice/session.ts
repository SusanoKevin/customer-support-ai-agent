// One live voice call: microphone -> Gemini Live -> speakers, in the browser.
// Imperative glue only. Protocol, sample conversion and UI state live in tested pure modules.
import { ChatRequestError, fetchVoiceToken } from "../api";
import { base64ToBytes, bytesToBase64, downsample, floatToPcm16, pcm16ToFloat } from "./pcm";
import { INPUT_SAMPLE_RATE, audioChunkMessage, liveUrl, parseServerMessage, setupMessage } from "./protocol";
import type { VoiceAction } from "./voiceState";

const WORKLET_URL = "/worklets/pcm-capture.js";
const NORMAL_CLOSE = 1000;

type Dispatch = (action: VoiceAction) => void;

function micErrorMessage(error: unknown): string {
  const name = error instanceof DOMException ? error.name : "";
  if (name === "NotAllowedError") return "Microphone access is blocked. Allow it in your browser's site settings, then try again.";
  if (name === "NotFoundError") return "No microphone was found. Connect one and try again.";
  return "The microphone couldn't start. Check that no other app is using it.";
}

export class VoiceSession {
  private ws: WebSocket | null = null;
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private capture: AudioWorkletNode | null = null;
  private sources = new Set<AudioBufferSourceNode>();
  private nextPlayAt = 0;
  private isStreaming = false;
  private isStopping = false;
  private readonly startAbort = new AbortController();
  micAnalyser: AnalyserNode | null = null;
  outputAnalyser: AnalyserNode | null = null;

  constructor(private readonly dispatch: Dispatch) {}

  /** Each await below can outlast an End call, so every step re-checks `isStopping` (log B3). */
  async start(sessionId: string): Promise<void> {
    this.dispatch({ type: "connecting" });
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (error) {
      if (!this.isStopping) this.fail(micErrorMessage(error), true);
      return;
    }
    if (this.isStopping) {
      stream.getTracks().forEach((t) => t.stop()); // granted after End call: release it at once
      return;
    }
    this.stream = stream;
    try {
      // Mic first: the token must be used within its new-session window, and the permission prompt can take a while.
      const token = await fetchVoiceToken(sessionId, this.startAbort.signal);
      if (this.isStopping) return;
      await this.buildAudioGraph();
      if (this.isStopping) return this.cleanup();
      this.openSocket(token.token, token.model);
    } catch (error) {
      if (this.isStopping) return; // the abort or a closed AudioContext, caused by End call itself
      const retryable = error instanceof ChatRequestError ? error.retryable : true;
      this.fail(error instanceof Error ? error.message : "Voice couldn't start.", retryable);
    }
  }

  stop(): void {
    this.isStopping = true;
    this.startAbort.abort();
    this.ws?.close(NORMAL_CLOSE);
    this.cleanup(); // detaches onclose, so "ended" is dispatched here rather than from the socket
    this.dispatch({ type: "ended" });
  }

  private async buildAudioGraph(): Promise<void> {
    const ctx = new AudioContext();
    this.ctx = ctx;
    await ctx.resume();
    await ctx.audioWorklet.addModule(WORKLET_URL);
    const mic = ctx.createMediaStreamSource(this.stream!);
    this.micAnalyser = new AnalyserNode(ctx, { fftSize: 1024 });
    this.outputAnalyser = new AnalyserNode(ctx, { fftSize: 1024 });
    this.outputAnalyser.connect(ctx.destination);
    this.capture = new AudioWorkletNode(ctx, "pcm-capture");
    this.capture.port.onmessage = (e: MessageEvent<Float32Array>) => this.sendMic(e.data);
    mic.connect(this.micAnalyser);
    mic.connect(this.capture); // the worklet outputs nothing, so the mic is never played back
  }

  private openSocket(token: string, model: string): void {
    const ws = new WebSocket(liveUrl(token));
    ws.binaryType = "arraybuffer"; // decode synchronously so frames stay in order
    this.ws = ws;
    const decoder = new TextDecoder();
    ws.onopen = () => ws.send(setupMessage(model));
    ws.onmessage = (e: MessageEvent<ArrayBuffer | string>) => {
      const raw = typeof e.data === "string" ? e.data : decoder.decode(e.data);
      for (const event of parseServerMessage(raw)) {
        if (event.type === "ready") this.isStreaming = true;
        else if (event.type === "audio") this.play(event.data, event.sampleRate);
        else if (event.type === "interrupted") this.stopPlayback();
        else if (event.type === "protocol_error") console.warn("Unreadable Live frame", raw.slice(0, 200));
        this.dispatch({ type: "live", event });
      }
    };
    ws.onclose = (e: CloseEvent) => {
      const byUs = this.isStopping;
      this.cleanup();
      if (byUs || e.code === NORMAL_CLOSE) this.dispatch({ type: "ended" });
      else this.fail(`The voice session closed unexpectedly (${e.code}${e.reason ? `: ${e.reason}` : ""}).`, true);
    };
  }

  private sendMic(frame: Float32Array): void {
    if (!this.isStreaming || !this.ctx || this.ws?.readyState !== WebSocket.OPEN) return;
    const pcm = floatToPcm16(downsample(frame, this.ctx.sampleRate, INPUT_SAMPLE_RATE));
    this.ws.send(audioChunkMessage(bytesToBase64(new Uint8Array(pcm.buffer))));
  }

  /** Queue each chunk right after the previous one so playback is gapless. */
  private play(base64: string, sampleRate: number): void {
    const ctx = this.ctx;
    if (!ctx || !this.outputAnalyser) return;
    const bytes = base64ToBytes(base64);
    const samples = pcm16ToFloat(new Int16Array(bytes.buffer, 0, bytes.length >> 1));
    if (samples.length === 0) return;
    const buffer = ctx.createBuffer(1, samples.length, sampleRate);
    buffer.copyToChannel(samples as Float32Array<ArrayBuffer>, 0);
    const source = new AudioBufferSourceNode(ctx, { buffer });
    source.connect(this.outputAnalyser);
    const startAt = Math.max(ctx.currentTime, this.nextPlayAt);
    source.start(startAt);
    this.nextPlayAt = startAt + buffer.duration;
    this.sources.add(source);
    source.onended = () => {
      this.sources.delete(source);
      if (this.sources.size === 0) this.dispatch({ type: "playback_idle" });
    };
  }

  /** Barge-in: the server heard the customer start talking, so drop everything still queued. */
  private stopPlayback(): void {
    for (const source of this.sources) {
      source.onended = null;
      source.stop();
    }
    this.sources.clear();
    this.nextPlayAt = 0;
  }

  private fail(message: string, retryable: boolean): void {
    this.cleanup();
    this.dispatch({ type: "failed", message, retryable });
  }

  private cleanup(): void {
    this.isStreaming = false;
    this.stopPlayback();
    if (this.capture) this.capture.port.onmessage = null;
    this.stream?.getTracks().forEach((t) => t.stop());
    void this.ctx?.close().catch(() => undefined);
    if (this.ws) {
      this.ws.onmessage = null;
      this.ws.onclose = null;
    }
    this.ws = null;
    this.ctx = null;
    this.stream = null;
    this.capture = null;
    this.micAnalyser = null;
    this.outputAnalyser = null;
  }
}
