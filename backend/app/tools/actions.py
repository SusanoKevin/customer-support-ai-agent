"""Tool 3: simulated actions.

Tier and contract status are always looked up from user_id on the server.
The model only supplies who, how much, and why, so it cannot talk its way
into a bigger refund.
"""

import uuid
from typing import Literal

from app.tools.accounts import Tier, find_account
from app.tools.base import ToolError, ToolResult

REFUND_LIMITS_USD: dict[Tier, float] = {"free": 0.0, "pro": 50.0, "enterprise": 500.0}

Priority = Literal["low", "normal", "high"]


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def issue_refund(user_id: str, amount_usd: float, reason: str) -> ToolResult:
    if amount_usd <= 0:
        raise ToolError("Refund amount must be positive", retryable=False)
    account = find_account(user_id)
    if account is None:
        raise ToolError(f"Unknown user_id: {user_id}", retryable=False)
    if not account.can_take_actions:
        return ToolResult(ok=False, data={"reason": "contract_not_active"})

    limit = REFUND_LIMITS_USD[account.tier]
    if amount_usd > limit:
        return ToolResult(ok=False, data={"reason": "over_tier_limit", "limit_usd": limit})

    return ToolResult(
        ok=True,
        data={
            "refund_id": _new_id("rf"),
            "user_id": user_id,
            "amount_usd": round(amount_usd, 2),
            "reason": reason,
        },
    )


def create_ticket(user_id: str | None, summary: str, reason: str, priority: Priority = "normal") -> ToolResult:
    if not summary.strip():
        raise ToolError("Ticket summary is required", retryable=False)
    return ToolResult(
        ok=True,
        data={
            "ticket_id": _new_id("tk"),
            "user_id": user_id,
            "summary": summary.strip(),
            "reason": reason,
            "priority": priority,
        },
    )
