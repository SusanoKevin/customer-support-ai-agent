"""Short-lived Gemini Live tokens for the browser.

The browser talks to Gemini Live directly (log D3), so it must never hold the real API key.
The backend mints a single-use ephemeral token with the model, system prompt, transcription
settings and the one voice tool locked: a client that sends a different config gets the locked one anyway.

Voice has one tool, `ask_support_agent`. The browser answers it by running a normal chat turn
on the same session, so voice gets every guard, template and trace the chat agent has (log D29).
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from google import genai
from google.genai import types

from app.agent.templates import VOICE_SYSTEM_PROMPT

logger = logging.getLogger("support_agent")

# Ephemeral tokens exist only on v1alpha (google-genai 3.6.1). The browser must connect to the
# matching BidiGenerateContentConstrained endpoint (frontend/lib/voice/protocol.ts).
LIVE_API_VERSION = "v1alpha"

VOICE_TOOL_NAME = "ask_support_agent"
# Kept short: the Live model only needs to know when to call it and what to pass.
VOICE_TOOL = types.Tool(function_declarations=[types.FunctionDeclaration(
    name=VOICE_TOOL_NAME,
    description=("Send the customer's request to the support agent, which can verify identity, look up charges, "
                 "check policy, issue refunds and open tickets. Returns the reply to read to the customer."),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={"message": types.Schema(
            type=types.Type.STRING,
            description="The customer's request in their own words, including any email and card last 4 digits they said.",
        )},
        required=["message"],
    ),
)])


class VoiceTokenError(Exception):
    """Minting failed upstream. The message is for logs, never for the browser."""


@dataclass(frozen=True)
class VoiceToken:
    token: str
    model: str
    expires_at: datetime
    new_session_expires_at: datetime


class VoiceTokenIssuer(Protocol):
    async def mint(self, session_id: str) -> VoiceToken: ...


def build_token_config(model: str, now: datetime, *, ttl_min: int, new_session_window_s: int) -> types.CreateAuthTokenConfig:
    """Single use; must be opened within the window; the session ends at `ttl_min`. Every set field is locked."""
    live = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        system_instruction=VOICE_SYSTEM_PROMPT,
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        tools=[VOICE_TOOL],
    )
    return types.CreateAuthTokenConfig(
        uses=1,
        expire_time=now + timedelta(minutes=ttl_min),
        new_session_expire_time=now + timedelta(seconds=new_session_window_s),
        live_connect_constraints=types.LiveConnectConstraints(model=model, config=live),
        lock_additional_fields=[],  # empty list = lock every field set above, leave the rest open
    )


class GeminiVoiceTokenIssuer:
    def __init__(self, api_key: str, model: str, ttl_min: int, new_session_window_s: int):
        self._client = genai.Client(api_key=api_key, http_options=types.HttpOptions(api_version=LIVE_API_VERSION))
        self._model = model
        self._ttl_min = ttl_min
        self._window_s = new_session_window_s

    async def mint(self, session_id: str) -> VoiceToken:
        now = datetime.now(UTC)
        config = build_token_config(self._model, now, ttl_min=self._ttl_min, new_session_window_s=self._window_s)
        try:
            token = await self._client.aio.auth_tokens.create(config=config)
        except Exception as exc:  # SDK raises several types; all mean "no token"
            raise VoiceTokenError(f"{type(exc).__name__}: {exc}") from exc
        if not token.name:
            raise VoiceTokenError("Token response had no name")
        logger.info("Minted voice token for session %s (model %s)", session_id, self._model)
        return VoiceToken(token=token.name, model=self._model, expires_at=config.expire_time,
                          new_session_expires_at=config.new_session_expire_time)
