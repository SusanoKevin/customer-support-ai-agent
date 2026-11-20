"""SSE event contract. Mirror of frontend/lib/events.ts; change both together."""

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict

StepState = Literal["started", "completed", "failed"]
Priority = Literal["low", "normal", "high"]


class Event(BaseModel):
    model_config = ConfigDict(frozen=True)
    event: ClassVar[str]

    def to_sse(self) -> dict[str, str]:
        """Format for sse_starlette.EventSourceResponse."""
        return {"event": self.event, "data": self.model_dump_json()}


class StatusEvent(Event):
    event = "status"
    step: str
    state: StepState
    label: str


class TokenEvent(Event):
    event = "token"
    text: str


class ToolEvent(Event):
    event = "tool"
    name: str
    input: dict[str, Any]
    output: dict[str, Any] | None
    ok: bool


class EscalationEvent(Event):
    event = "escalation"
    reason: str
    ticket_id: str | None
    priority: Priority | None = None


class TraceEvent(Event):
    event = "trace"
    step: str
    latency_ms: float
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


class ErrorEvent(Event):
    event = "error"
    code: str
    message: str
    retryable: bool


class DoneEvent(Event):
    event = "done"
    session_id: str
