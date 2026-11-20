"""/api/chat over HTTP with injected fakes: event order, validation, and the error path."""

import json

import httpx

from app.main import create_app
from tests.test_orchestrator import MAYA, C, make_deps


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.replace("\r\n", "\n").strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
        if "event" in lines:
            events.append((lines["event"], json.loads(lines["data"])))
    return events


async def _post(app, payload: dict) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/api/chat", json=payload)


async def test_chat_streams_status_tool_token_done_in_order():
    app = create_app(deps=make_deps(C("refund_request", amount_usd=30, **MAYA)))
    response = await _post(app, {"session_id": "session-0001", "message": "Refund $30 please"})
    assert response.status_code == 200
    names = [name for name, _ in _parse_sse(response.text)]
    assert names[0] == "status"
    assert names.index("tool") < names.index("token") < names.index("done")
    assert names[-1] == "done"


async def test_chat_rejects_empty_message_and_bad_session_id():
    app = create_app(deps=make_deps())
    assert (await _post(app, {"session_id": "session-0001", "message": ""})).status_code == 422
    assert (await _post(app, {"session_id": "bad id!", "message": "hi"})).status_code == 422


async def test_unexpected_failure_still_ends_with_error_then_done():
    class BrokenLLM:
        async def classify(self, message, recent_turns):
            raise RuntimeError("boom")

    deps = make_deps()
    app = create_app(deps=type(deps)(**{**deps.__dict__, "llm": BrokenLLM()}))
    events = _parse_sse((await _post(app, {"session_id": "session-0001", "message": "hi"})).text)
    assert [name for name, _ in events][-2:] == ["error", "done"]
    assert events[-2][1]["code"] == "internal_error"
    assert "boom" not in json.dumps(events)  # internal details stay in the server log
