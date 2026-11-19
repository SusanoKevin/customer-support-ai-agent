"""Shared tool types. Tools are pure functions over immutable inputs."""

import random
from dataclasses import dataclass
from typing import Any


class ToolError(Exception):
    """Raised when a tool fails. `retryable` tells the orchestrator whether to retry."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    data: dict[str, Any]


def maybe_fail(tool_name: str, failure_rate: float, rng: random.Random | None = None) -> None:
    """Simulated upstream failure for the resilience demo."""
    roll = (rng or random).random()
    if roll < failure_rate:
        raise ToolError(f"{tool_name}: simulated upstream timeout", retryable=True)
