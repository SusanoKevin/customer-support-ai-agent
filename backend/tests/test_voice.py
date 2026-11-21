"""Voice token endpoint and the locked Live config. No network: the issuer is faked or only its config is built."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agent.templates import VOICE_SYSTEM_PROMPT
from app.config import Settings
from app.main import create_app
from app.voice import VOICE_TOOL_NAME, GeminiVoiceTokenIssuer, VoiceToken, VoiceTokenError, build_token_config
from tests.test_orchestrator import make_deps

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
SID = "session-voice-01"


class FakeIssuer:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls: list[str] = []

    async def mint(self, session_id: str) -> VoiceToken:
        self.calls.append(session_id)
        if self.error:
            raise self.error
        return VoiceToken(token="auth_tokens/fake", model="gemini-3.8-live",
                          expires_at=NOW + timedelta(minutes=30), new_session_expires_at=NOW + timedelta(minutes=1))


def client_with(issuer: FakeIssuer | None, settings: Settings | None = None) -> TestClient:
    deps = make_deps()
    deps = replace(deps, voice=issuer, settings=settings or deps.settings)
    return TestClient(create_app(deps=deps))


def test_token_endpoint_returns_short_lived_token_and_model():
    issuer = FakeIssuer()
    r = client_with(issuer).post("/api/voice/token", json={"session_id": SID})
    assert r.status_code == 200
    body = r.json()
    assert body["token"] == "auth_tokens/fake"
    assert body["model"] == "gemini-3.8-live"
    assert body["expires_at"].startswith("2026-11-22T12:30")
    assert issuer.calls == [SID]
    assert r.headers["cache-control"] == "no-store"


def test_token_endpoint_never_returns_the_api_key():
    settings = Settings(_env_file=None, gemini_api_key="real-secret-key")
    r = client_with(FakeIssuer(), settings).post("/api/voice/token", json={"session_id": SID})
    assert r.status_code == 200
    assert "real-secret-key" not in r.text


def test_token_endpoint_rejects_bad_session_id():
    r = client_with(FakeIssuer()).post("/api/voice/token", json={"session_id": "bad id!"})
    assert r.status_code == 422


def test_token_endpoint_503_when_voice_not_configured():
    r = client_with(None).post("/api/voice/token", json={"session_id": SID})
    assert r.status_code == 503
    assert r.json()["detail"]["retryable"] is False


def test_token_endpoint_503_retryable_when_minting_fails():
    r = client_with(FakeIssuer(VoiceTokenError("upstream 500"))).post("/api/voice/token", json={"session_id": SID})
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["retryable"] is True
    assert "upstream" not in detail["message"]  # internal detail stays in the server log


def test_token_config_is_single_use_and_short_lived():
    cfg = build_token_config("gemini-3.8-live", NOW, ttl_min=30, new_session_window_s=60)
    assert cfg.uses == 1
    assert cfg.expire_time == NOW + timedelta(minutes=30)
    assert cfg.new_session_expire_time == NOW + timedelta(seconds=60)


def test_token_config_locks_model_prompt_and_transcription():
    """The browser cannot swap the model or the instructions: every set field is locked (empty lock list)."""
    cfg = build_token_config("gemini-3.8-live", NOW, ttl_min=30, new_session_window_s=60)
    live = cfg.live_connect_constraints
    assert live.model == "gemini-3.8-live"
    assert [str(getattr(m, "value", m)) for m in live.config.response_modalities] == ["AUDIO"]
    assert live.config.system_instruction == VOICE_SYSTEM_PROMPT
    assert live.config.input_audio_transcription is not None
    assert live.config.output_audio_transcription is not None
    assert cfg.lock_additional_fields == []


def test_token_config_locks_one_tool_that_delegates_to_the_chat_agent():
    """Voice gets exactly one tool. Account work goes through the same orchestrator as chat (log D29)."""
    cfg = build_token_config("gemini-3.8-live", NOW, ttl_min=30, new_session_window_s=60)
    tools = cfg.live_connect_constraints.config.tools
    declarations = [d for t in tools for d in t.function_declarations]
    assert [d.name for d in declarations] == [VOICE_TOOL_NAME]
    assert declarations[0].parameters.required == ["message"]
    assert "approve_refund" not in str(tools) and "issue_refund" not in str(tools)


def test_voice_prompt_sends_account_work_to_the_tool_and_never_decides_itself():
    prompt = VOICE_SYSTEM_PROMPT.lower()
    assert VOICE_TOOL_NAME in prompt
    assert "refund" in prompt and "never" in prompt
    assert "one moment" in prompt  # filler line while the agent works


class _FakeAuthTokens:
    def __init__(self, name: str | None = "auth_tokens/abc", error: Exception | None = None):
        self.name, self.error, self.configs = name, error, []

    async def create(self, config):
        self.configs.append(config)
        if self.error:
            raise self.error
        return SimpleNamespace(name=self.name)


def _issuer_with(auth_tokens: _FakeAuthTokens) -> GeminiVoiceTokenIssuer:
    issuer = GeminiVoiceTokenIssuer("key", "gemini-3.8-live", ttl_min=30, new_session_window_s=60)
    issuer._client = SimpleNamespace(aio=SimpleNamespace(auth_tokens=auth_tokens))
    return issuer


async def test_gemini_issuer_returns_token_with_locked_config():
    fake = _FakeAuthTokens()
    token = await _issuer_with(fake).mint(SID)
    assert token.token == "auth_tokens/abc" and token.model == "gemini-3.8-live"
    assert token.expires_at - token.new_session_expires_at == timedelta(minutes=29)
    assert fake.configs[0].live_connect_constraints.model == "gemini-3.8-live"


async def test_gemini_issuer_wraps_sdk_errors():
    with pytest.raises(VoiceTokenError, match="RuntimeError"):
        await _issuer_with(_FakeAuthTokens(error=RuntimeError("boom"))).mint(SID)


async def test_gemini_issuer_rejects_a_token_without_a_name():
    with pytest.raises(VoiceTokenError, match="no name"):
        await _issuer_with(_FakeAuthTokens(name=None)).mint(SID)
