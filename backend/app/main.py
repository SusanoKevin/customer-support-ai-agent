"""FastAPI entrypoint. Routes are wired; handlers fill in on Days 2 and 4."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.config import get_settings

settings = get_settings()
app = FastAPI(title="Customer Support Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    message: str = Field(min_length=1, max_length=2000)


@app.get("/health")
async def health() -> dict[str, str]:
    """Also used to warm the free Render instance before the demo."""
    return {"status": "ok"}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """TODO Day 2: rate limit, load session, EventSourceResponse(run_turn(...))."""
    raise NotImplementedError


@app.post("/api/voice/token")
async def voice_token():
    """TODO Day 4: mint a short-lived Gemini Live ephemeral token. Never return the real key."""
    raise NotImplementedError


@app.post("/api/tools/{name}")
async def run_tool(name: str):
    """TODO Day 5: voice-mode tool calls land here so chat and voice share one tool layer."""
    raise NotImplementedError


@app.get("/api/sessions/{session_id}/trace")
async def session_trace(session_id: str):
    """TODO Day 3: trace rows for the observability drawer."""
    raise NotImplementedError
