# Frontend

Next.js chat client for the support agent. Run the backend on port 8000 first.

```bash
npm install
npm run dev     # http://localhost:3000
npm test        # unit tests for the SSE parser, conversation reducer and citations
```

Set `NEXT_PUBLIC_API_BASE` to point at a deployed backend (default `http://localhost:8000`).

Components (voice ones arrive with the voice work):

```
app/page.tsx                       two-pane layout: conversation + observability drawer
components/chat/ChatPanel.tsx      input, message list, SSE reader (fetch + ReadableStream, POST body)
components/chat/StepIndicator.tsx  renders `status` events as a live checklist
components/chat/ToolCard.tsx       renders `tool` events
components/chat/EscalationBanner.tsx
components/voice/VoiceToggle.tsx   starts Gemini Live session with token from /api/voice/token
components/voice/Waveform.tsx      Web Audio AnalyserNode on mic + output streams
components/voice/LiveTranscript.tsx
components/observability/TraceDrawer.tsx  latency, tokens, cost per step; totals row
lib/sse.ts                         parse `event:` / `data:` frames into AgentEvent
lib/session.ts                     session_id in sessionStorage, shared by chat and voice
```

Use `fetch` + stream reader instead of `EventSource`, because `EventSource` cannot send a POST body.
