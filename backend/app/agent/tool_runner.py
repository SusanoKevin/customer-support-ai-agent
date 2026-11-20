"""Runs one tool call with simulated failures, one retry, and the events the UI shows."""

import asyncio
import inspect
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.events import ErrorEvent, Event, StatusEvent, ToolEvent
from app.tools.base import ToolError, ToolResult, maybe_fail

# Escalation must keep working during the failure demo, so ticket creation is never failed on purpose.
SIMULATION_EXEMPT = frozenset({"create_ticket"})
HIDDEN_INPUTS = frozenset({"records", "ledger", "store", "retriever", "today"})
MASKED_INPUTS = frozenset({"last4"})


@dataclass(frozen=True)
class ToolCall:
    name: str
    result: ToolResult | None
    error: ToolError | None
    events: tuple[Event, ...]

    @property
    def log_entry(self) -> str:
        if self.error is not None:
            return f"{self.name}: error"
        if self.result is not None and not self.result.ok:
            return f"{self.name}: {self.result.data.get('reason', 'not ok')}"
        return f"{self.name}: ok"


def _shown(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Inputs as the observability drawer shows them: no internal objects, card digits masked."""
    def show(key: str, value: Any) -> Any:
        if key in MASKED_INPUTS:
            return "****"
        return value.isoformat() if isinstance(value, date) else value
    return {k: show(k, v) for k, v in kwargs.items() if k not in HIDDEN_INPUTS}


async def _invoke(fn: Callable[..., Any], kwargs: dict[str, Any]) -> ToolResult:
    result = fn(**kwargs)
    return await result if inspect.isawaitable(result) else result


async def run_tool(name: str, fn: Callable[..., Any], kwargs: dict[str, Any], *, failure_rate: float,
                   rng: random.Random, retry_delay_s: float) -> ToolCall:
    shown = _shown(kwargs)
    events: list[Event] = []
    error: ToolError | None = None
    for attempt in (1, 2):
        try:
            if name not in SIMULATION_EXEMPT:
                maybe_fail(name, failure_rate, rng)
            result = await _invoke(fn, kwargs)
            events.append(ToolEvent(name=name, input=shown, output=result.data, ok=result.ok))
            return ToolCall(name=name, result=result, error=None, events=tuple(events))
        except ToolError as exc:
            error = exc
            if not exc.retryable or attempt == 2:
                break
            events.append(StatusEvent(step=name, state="failed", label="Temporary problem, retrying..."))
            await asyncio.sleep(retry_delay_s)

    events.append(ToolEvent(name=name, input=shown, output={"error": str(error)}, ok=False))
    events.append(ErrorEvent(code="tool_failed", message=f"{name} could not be completed",
                             retryable=bool(error and error.retryable)))
    return ToolCall(name=name, result=None, error=error, events=tuple(events))
