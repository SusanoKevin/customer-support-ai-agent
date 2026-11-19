"""Tool 1: verify identity, subscription tier, and contract status."""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from app.tools.base import ToolError, ToolResult

Tier = Literal["free", "pro", "enterprise"]
ContractStatus = Literal["active", "expired", "suspended"]

ACCOUNTS_PATH = Path(__file__).resolve().parents[2] / "data" / "mock_accounts.json"


@dataclass(frozen=True)
class Account:
    user_id: str
    email: str
    name: str
    tier: Tier
    contract_status: ContractStatus
    last4: str

    @property
    def can_take_actions(self) -> bool:
        return self.contract_status == "active"


@lru_cache
def load_accounts() -> tuple[Account, ...]:
    return tuple(Account(**row) for row in json.loads(ACCOUNTS_PATH.read_text()))


def find_account(user_id: str) -> Account | None:
    return next((a for a in load_accounts() if a.user_id == user_id), None)


def verify_account(email: str, last4: str) -> ToolResult:
    normalized = email.strip().lower()
    if "@" not in normalized:
        raise ToolError("A valid email is required", retryable=False)

    match = next((a for a in load_accounts() if a.email == normalized), None)
    if match is None or match.last4 != last4.strip():
        return ToolResult(ok=False, data={"reason": "identity_not_verified"})

    return ToolResult(
        ok=True,
        data={
            "user_id": match.user_id,
            "name": match.name,
            "tier": match.tier,
            "contract_status": match.contract_status,
            "can_take_actions": match.can_take_actions,
        },
    )
