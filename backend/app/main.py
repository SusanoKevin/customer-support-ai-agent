"""FastAPI entrypoint. `/api/chat` streams agent turns (chat and voice both use it, log D29); `/api/voice/token` mints Live tokens."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.agent.deps import Deps
from app.agent.llm import GeminiLLM
from app.agent.orchestrator import run_turn
from app.agent.sessions import InMemorySessionStore
from app.config import Settings, get_settings
from app.db import apply_schema, make_pool
from app.events import DoneEvent, ErrorEvent
from app.rag.embeddings import GeminiEmbedder
from app.rag.retriever import PgVectorRetriever
from app.tools.billing import load_billing
from app.tools.stores import InMemoryRefundLedger, InMemoryTicketStore
from app.voice import GeminiVoiceTokenIssuer, VoiceTokenError, VoiceTokenIssuer

logger = logging.getLogger("support_agent")


# Matches ID_PATTERN in frontend/lib/session.ts.
SessionId = Annotated[str, Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]


class ChatRequest(BaseModel):
    session_id: SessionId
    message: str = Field(min_length=1, max_length=2000)


class VoiceTokenRequest(BaseModel):
    session_id: SessionId


class VoiceTokenResponse(BaseModel):
    token: str
    model: str
    expires_at: str
    new_session_expires_at: str


def _voice_issuer(settings: Settings) -> VoiceTokenIssuer | None:
    if not (settings.gemini_api_key and settings.gemini_live_model):
        logger.warning("Voice disabled: GEMINI_API_KEY or GEMINI_LIVE_MODEL is empty")
        return None
    return GeminiVoiceTokenIssuer(settings.gemini_api_key, settings.gemini_live_model,
                                  settings.voice_token_ttl_min, settings.voice_new_session_window_s)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Schema first on one plain connection, then the pool (see the Supabase notes in db.py)."""
    settings: Settings = app.state.settings
    await apply_schema(settings.database_url)
    pool = make_pool(settings.database_url)
    await pool.open()
    records = load_billing()
    embedder = GeminiEmbedder(settings.gemini_api_key, settings.gemini_embed_model, settings.embed_dim)
    app.state.deps = Deps(
        llm=GeminiLLM(settings.gemini_api_key, settings.gemini_classify_model,
                      settings.gemini_answer_model, settings.llm_timeout_s,
                      answer_thinking_level=settings.gemini_answer_thinking_level),
        retriever=PgVectorRetriever(pool, embedder),
        records=records,
        ledger=InMemoryRefundLedger(records.refunds),
        tickets=InMemoryTicketStore(),
        sessions=InMemorySessionStore(),
        settings=settings,
        voice=_voice_issuer(settings),
    )
    try:
        yield
    finally:
        await pool.close()


def get_deps(request: Request) -> Deps:
    return request.app.state.deps


async def _sse(req: ChatRequest, deps: Deps) -> AsyncIterator[dict[str, str]]:
    """Every stream ends with `done`, even when something unexpected fails mid-turn."""
    try:
        async for event in run_turn(req.session_id, req.message, deps):
            yield event.to_sse()
    except Exception:
        logger.exception("Chat turn failed for session %s", req.session_id)
        yield ErrorEvent(code="internal_error", message="Something went wrong on our side.", retryable=True).to_sse()
        yield DoneEvent(session_id=req.session_id).to_sse()


def create_app(deps: Deps | None = None, settings: Settings | None = None) -> FastAPI:
    """Pass `deps` to skip startup wiring (tests inject fakes; no database or Gemini)."""
    settings = settings or (deps.settings if deps else get_settings())
    app = FastAPI(title="Customer Support Agent", lifespan=None if deps else _lifespan)
    app.state.settings = settings
    if deps is not None:
        app.state.deps = deps
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Also used to warm the free Render instance before the demo."""
        return {"status": "ok"}

    @app.post("/api/chat")
    async def chat(req: ChatRequest, deps: Deps = Depends(get_deps)) -> EventSourceResponse:
        """Rate limiting is added on Day 6 (log P1)."""
        return EventSourceResponse(_sse(req, deps))

    @app.post("/api/voice/token", response_model=VoiceTokenResponse)
    async def voice_token(req: VoiceTokenRequest, response: Response, deps: Deps = Depends(get_deps)) -> VoiceTokenResponse:
        """Single-use, short-lived token with the model and prompt locked (app/voice.py). Never the real key."""
        if deps.voice is None:
            raise HTTPException(503, {"message": "Voice isn't available on this server.", "retryable": False})
        try:
            minted = await deps.voice.mint(req.session_id)
        except VoiceTokenError:
            logger.exception("Voice token mint failed for session %s", req.session_id)
            raise HTTPException(503, {"message": "Voice couldn't start. Please try again in a moment.", "retryable": True}) from None
        response.headers["Cache-Control"] = "no-store"
        return VoiceTokenResponse(token=minted.token, model=minted.model, expires_at=minted.expires_at.isoformat(),
                                  new_session_expires_at=minted.new_session_expires_at.isoformat())

    @app.get("/api/sessions/{session_id}/trace")
    async def session_trace(session_id: str):
        """TODO Day 5: trace rows for the observability drawer, so a reload can restore them (L17)."""
        raise NotImplementedError

    return app


app = create_app()
