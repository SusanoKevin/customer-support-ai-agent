"""Sliding-window limits: the limiter itself, the HTTP routes, and failed identity checks per email."""

import httpx
import pytest
from dataclasses import replace
from starlette.requests import Request

from app.agent import templates
from app.config import Settings
from app.main import client_ip, create_app
from app.ratelimit import SlidingWindowLimiter
from tests.test_orchestrator import C, make_deps, text, tools, turn
from tests.test_voice import FakeIssuer


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_limiter_allows_up_to_the_limit_then_reports_seconds_to_wait():
    clock = Clock()
    limiter = SlidingWindowLimiter(limit=2, window_s=60, clock=clock)
    assert limiter.hit("a") is None
    clock.now += 10
    assert limiter.hit("a") is None
    assert limiter.hit("a") == pytest.approx(50)  # the first hit leaves the window in 50 s


def test_limiter_frees_a_slot_when_the_oldest_hit_leaves_the_window():
    clock = Clock()
    limiter = SlidingWindowLimiter(limit=1, window_s=60, clock=clock)
    assert limiter.hit("a") is None
    clock.now += 60
    assert limiter.hit("a") is None


def test_limiter_keys_are_independent_and_check_does_not_count():
    limiter = SlidingWindowLimiter(limit=1, window_s=60, clock=Clock())
    assert limiter.check("a") is None and limiter.check("a") is None
    assert limiter.hit("a") is None
    assert limiter.hit("b") is None
    assert limiter.check("a") is not None


def test_limiter_drops_keys_whose_hits_have_all_expired():
    clock = Clock()
    limiter = SlidingWindowLimiter(limit=5, window_s=60, clock=clock)
    for key in ("a", "b", "c"):
        limiter.hit(key)
    clock.now += 61
    limiter.hit("d")
    assert limiter.tracked_keys == 1  # memory stays bounded by active clients


def _request(headers: dict[str, str], host: str = "10.0.0.1") -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw, "client": (host, 1234)})


def test_client_ip_uses_the_socket_unless_a_trusted_header_is_configured():
    spoofed = {"x-forwarded-for": "1.2.3.4", "true-client-ip": "5.6.7.8"}
    assert client_ip(_request(spoofed), "") == "10.0.0.1"
    assert client_ip(_request(spoofed), "true-client-ip") == "5.6.7.8"
    assert client_ip(_request({}), "true-client-ip") == "10.0.0.1"  # header missing: fall back


def _app(**settings):
    deps = make_deps()
    deps = replace(deps, settings=Settings(_env_file=None, **settings), voice=FakeIssuer())
    return create_app(deps=deps)


async def _post(app, path: str, payload: dict) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(path, json=payload)


async def test_chat_returns_429_with_retry_after_once_a_session_is_over_its_limit():
    app = _app(rate_limit_per_minute=2)
    body = {"session_id": "session-0001", "message": "hi"}
    assert (await _post(app, "/api/chat", body)).status_code == 200
    assert (await _post(app, "/api/chat", body)).status_code == 200
    over = await _post(app, "/api/chat", body)
    assert over.status_code == 429
    assert int(over.headers["retry-after"]) >= 1
    assert over.json()["detail"]["retryable"] is True
    assert "wait" in over.json()["detail"]["message"]
    other = await _post(app, "/api/chat", {"session_id": "session-0002", "message": "hi"})
    assert other.status_code == 200  # the cap is per session


async def test_chat_is_also_capped_per_ip_so_new_session_ids_do_not_get_around_it():
    app = _app(rate_limit_per_minute=100, rate_limit_ip_per_minute=2)
    for n in (1, 2):
        assert (await _post(app, "/api/chat", {"session_id": f"session-000{n}", "message": "hi"})).status_code == 200
    assert (await _post(app, "/api/chat", {"session_id": "session-0003", "message": "hi"})).status_code == 429


async def test_voice_tokens_are_capped_per_ip():
    app = _app(voice_tokens_per_hour=1)
    assert (await _post(app, "/api/voice/token", {"session_id": "session-0001"})).status_code == 200
    over = await _post(app, "/api/voice/token", {"session_id": "session-0002"})
    assert over.status_code == 429 and over.json()["detail"]["retryable"] is True


async def test_failed_checks_on_one_email_lock_it_across_sessions():  # P16, closes the gap B5 left
    wrong = [C("provide_identity", email="maya@example.com", last4=f"{d}{d}{d}{d}") for d in range(1, 6)]
    deps = make_deps(*wrong, C("provide_identity", email="maya@example.com", last4="4242"))
    for n in range(5):  # a new session each time, so the per-session lockout never triggers
        await turn(deps, sid=f"session-guess-{n}")
    locked = await turn(deps, sid="session-guess-final")
    assert tools(locked) == []  # the correct code is never even checked
    assert text(locked) == templates.EMAIL_LOCKED
    assert deps.sessions.get("session-guess-final").account is None


async def test_email_lock_is_by_email_not_by_session():
    wrong = [C("provide_identity", email="maya@example.com", last4="1111") for _ in range(5)]
    deps = make_deps(*wrong, C("provide_identity", email="dev@example.com", last4="1881"))
    for n in range(5):
        await turn(deps, sid=f"session-guess-{n}")
    other = await turn(deps, sid="session-guess-final")
    assert tools(other) == ["verify_account"]
    assert deps.sessions.get("session-guess-final").account is not None
