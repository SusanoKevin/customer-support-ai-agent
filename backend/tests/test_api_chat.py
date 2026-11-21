"""/api/chat over HTTP with injected fakes: event order, validation, and the error path."""

import asyncio
import json
from dataclasses import replace

import httpx

from app.main import create_app
from app.tools.stores import DemoWorkspaces
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


async def test_unfinished_trace_route_is_not_served():  # review M3
    transport = httpx.ASGITransport(app=create_app(deps=make_deps()))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/sessions/session-0001/trace")).status_code == 404


class _SlowLLM:
    """Yields to the event loop in classify, like a real network call, so concurrent turns interleave."""

    def __init__(self, inner) -> None:
        self.inner = inner

    async def classify(self, message, recent_turns):
        await asyncio.sleep(0.05)
        return await self.inner.classify(message, recent_turns)

    async def generate(self, system, prompt):
        return await self.inner.generate(system, prompt)


async def test_turns_on_one_session_run_one_at_a_time():  # review M2, log L13
    deps = make_deps(C("provide_identity", **MAYA), C("refund_request", amount_usd=20, charge_ref="in_m1"), C("other"))
    deps = replace(deps, llm=_SlowLLM(deps.llm))
    app = create_app(deps=deps)
    await _post(app, {"session_id": "session-0001", "message": "maya@example.com 4242"})
    await asyncio.gather(_post(app, {"session_id": "session-0001", "message": "refund $20 on in_m1"}),
                         _post(app, {"session_id": "session-0001", "message": "hello"}))
    state = deps.sessions.get("session-0001")
    customer = [t for role, t in state.history if role == "customer"]
    assert state.turn == 3
    assert sorted(customer[1:]) == ["hello", "refund $20 on in_m1"]


def _refund_ok(response: httpx.Response) -> bool:
    return any(name == "tool" and data["name"] == "issue_refund" and data["ok"]
               for name, data in _parse_sse(response.text))


async def test_each_visitor_gets_their_own_copy_of_the_demo_billing_data():  # review H1
    refund = C("refund_request", amount_usd=30, charge_ref="in_m1", **MAYA)
    deps = make_deps(refund, refund, refund)
    app = create_app(deps=replace(deps, workspaces=DemoWorkspaces(deps.records.refunds)))
    first = await _post(app, {"session_id": "session-a001", "workspace_id": "visitor-a1", "message": "refund"})
    other = await _post(app, {"session_id": "session-b001", "workspace_id": "visitor-b1", "message": "refund"})
    again = await _post(app, {"session_id": "session-a002", "workspace_id": "visitor-a1", "message": "refund"})
    assert _refund_ok(first) and _refund_ok(other)
    assert not _refund_ok(again)  # one visitor's "New session" keeps their refund history
