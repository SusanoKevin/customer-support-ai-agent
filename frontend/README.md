# Frontend

Next.js client for the support agent: a floating support chat on a mock product page, with live voice from the mic button and an observability view. See the root `README.md` for the whole system. Run the backend on port 8000 first.

```bash
npm install
npm run dev     # http://localhost:3000
npm test        # vitest: lib/__tests__ and lib/voice/__tests__
npx tsc --noEmit && npm run lint
```

Set `NEXT_PUBLIC_API_BASE` to point at a deployed backend (default `http://localhost:8000`). It is inlined at build time, so never put a secret in it.

```
app/page.tsx                          mock product landing page (fictional Acme Projects) with the widget on top
components/SupportWidget.tsx          floating launcher and panel (chat, voice, trace views), one agent turn runner shared by chat and voice
components/chat/                      Composer (with the mic that starts a call), MessageBubble, StepIndicator (status events), ToolCard, EscalationBanner
components/voice/useVoiceCall.ts      call state, start and stop; owned by the widget so the mic starts audio inside its click
components/voice/VoicePanel.tsx       Start/End call, status, transcript
components/voice/Waveform.tsx         canvas from an AnalyserNode (mic while listening, agent while speaking)
components/observability/TraceDrawer.tsx  latency, tokens and cost per step; turn and session totals
lib/api.ts                            POST /api/chat (SSE) and /api/voice/token, with retryable errors
lib/sse.ts                            parse `event:` / `data:` frames into AgentEvent
lib/conversation.ts                   pure reducer for the shared transcript and trace rows
lib/events.ts                         SSE contract, mirrors backend/app/events.py
lib/session.ts                        session_id in sessionStorage, shared by chat and voice
lib/citations.ts                      split or strip [doc:section:window] citations
lib/voice/protocol.ts                 Gemini Live wire format (setup, audio, tool calls)
lib/voice/pcm.ts                      16 kHz capture and 24 kHz playback conversion
lib/voice/voiceState.ts               pure reducer for the voice panel
lib/voice/tools.ts                    answers the one voice tool with a chat turn
lib/voice/session.ts                  mic, socket and playback glue
public/worklets/pcm-capture.js        AudioWorklet that posts 40 ms mic frames
```

Chat uses `fetch` plus a stream reader instead of `EventSource`, because `EventSource` cannot send a POST body.
