"""Tools the model may trigger, by name. Chat (orchestrator) and voice (/api/tools/{name}) share this list.

`approve_refund` is deliberately absent: only a human reviewer can approve beyond the tier
limit, so no model, prompt or voice call can reach it.
"""

from collections.abc import Callable
from types import MappingProxyType
from typing import Any

from app.tools.accounts import verify_account
from app.tools.actions import create_ticket, issue_refund
from app.tools.billing import get_refund_status, lookup_charges
from app.tools.policies import retrieve_policy

MODEL_TOOLS: MappingProxyType[str, Callable[..., Any]] = MappingProxyType({
    "verify_account": verify_account,
    "lookup_charges": lookup_charges,
    "get_refund_status": get_refund_status,
    "retrieve_policy": retrieve_policy,
    "issue_refund": issue_refund,
    "create_ticket": create_ticket,
})
