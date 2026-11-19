import json

import pytest
from pydantic import ValidationError

from app.events import DoneEvent, Event, StatusEvent, ToolEvent

FRONTEND_EVENT_NAMES = {"status", "token", "tool", "escalation", "trace", "error", "done"}


def test_to_sse_uses_event_name_and_json_payload():
    sse = StatusEvent(step="verify_account", state="started", label="Verifying Account Tier...").to_sse()
    assert sse["event"] == "status"
    assert json.loads(sse["data"]) == {"step": "verify_account", "state": "started", "label": "Verifying Account Tier..."}


def test_tool_event_keeps_name_field_in_payload():
    sse = ToolEvent(name="issue_refund", input={}, output=None, ok=False).to_sse()
    assert sse["event"] == "tool"
    assert json.loads(sse["data"])["name"] == "issue_refund"


def test_backend_events_match_frontend_contract():
    assert {cls.event for cls in Event.__subclasses__()} == FRONTEND_EVENT_NAMES


def test_events_are_immutable():
    event = DoneEvent(session_id="abc12345")
    with pytest.raises(ValidationError):
        event.session_id = "changed"
