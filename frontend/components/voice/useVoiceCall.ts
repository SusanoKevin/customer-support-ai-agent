"use client";
import { useCallback, useEffect, useReducer, useRef } from "react";
import { VoiceSession } from "@/lib/voice/session";
import type { AskAgent } from "@/lib/voice/tools";
import { initialVoice, voiceReducer, type VoiceStatus } from "@/lib/voice/voiceState";

const ACTIVE: ReadonlySet<VoiceStatus> = new Set(["connecting", "listening", "checking", "speaking"]);

/**
 * One live voice call. Lives above the voice view so the mic button can call `start`
 * inside its own click: iOS Safari only starts audio from a user gesture (log P12).
 */
export function useVoiceCall(sessionId: string, ask: AskAgent) {
  const [state, dispatch] = useReducer(voiceReducer, undefined, initialVoice);
  const sessionRef = useRef<VoiceSession | null>(null);
  const statusRef = useRef(state.status);
  const isActive = ACTIVE.has(state.status);

  useEffect(() => {
    statusRef.current = state.status;
  }, [state.status]);

  // Ends the call on unmount, and when "New session" changes the session id.
  useEffect(() => () => sessionRef.current?.stop(), [sessionId]);

  const getAnalyser = useCallback(() => {
    const session = sessionRef.current;
    if (!session) return null;
    return statusRef.current === "speaking" ? session.outputAnalyser : session.micAnalyser;
  }, []);

  function start() {
    if (!sessionId || isActive) return;
    const session = new VoiceSession(dispatch, ask);
    sessionRef.current = session;
    void session.start(sessionId);
  }

  function stop() {
    sessionRef.current?.stop();
  }

  return { state, isActive, start, stop, getAnalyser };
}

export type VoiceCall = ReturnType<typeof useVoiceCall>;
