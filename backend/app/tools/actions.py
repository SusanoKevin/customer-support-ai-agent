"""Tool 3: refund and ticket actions.

Tier, contract status, and every billing fact are looked up from records on the server.
The model only supplies who, which charge, how much, and why, so it cannot talk its way
into a bigger refund. `approve_refund` is for human reviewers and is not a model tool.
"""

import uuid
from dataclasses import replace
from datetime import date, timedelta
from types import MappingProxyType
from typing import Any

from app.tools.accounts import Account, Tier, find_account
from app.tools.base import ToolError, ToolResult
from app.tools.billing import BillingRecords, ChargeView, Refund, find_charge_view, refund_as_dict
from app.tools.stores import Priority, RefundLedger, Ticket, TicketStore

# Limits apply to the total refunded on one charge, across all requests (D19 rule 8).
REFUND_LIMITS_USD: dict[Tier, float] = {"free": 0.0, "pro": 50.0, "enterprise": 500.0}
REFUND_FREQUENCY_DAYS = 90
HIGH_PRIORITY_REASONS = frozenset({"security_or_legal", "outage"})
ENTERPRISE_HIGH_REASONS = frozenset({
    "over_tier_limit", "duplicate_charge", "billed_after_cancellation", "refund_failed",
    "outside_refund_window", "refund_appeal", "charge_dispute_unresolved",
})


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def ticket_priority(reason: str, tier: Tier | None) -> Priority:
    """Escalation policy: security, legal and outages are high; Enterprise refund escalations are high."""
    if reason in HIGH_PRIORITY_REASONS:
        return "high"
    if tier == "enterprise" and reason in ENTERPRISE_HIGH_REASONS:
        return "high"
    return "normal"


def _require_account(user_id: str) -> Account:
    account = find_account(user_id)
    if account is None:
        raise ToolError(f"Unknown user_id: {user_id}", retryable=False)
    return account


def _recent_agent_refund(ledger: RefundLedger, user_id: str, today: date) -> bool:
    since = today - timedelta(days=REFUND_FREQUENCY_DAYS)
    return any(r.kind == "agent" and r.counts_against_charge and r.created_at >= since
               for r in ledger.refunds_for(user_id))


def _refund_block(account: Account, view: ChargeView | None, amount: float, ledger: RefundLedger,
                  today: date) -> dict[str, Any] | None:
    """Return the first rule that blocks this refund, checked in a fixed order, or None."""
    if view is None:
        return {"reason": "charge_not_found"}
    if not account.can_take_actions:
        return {"reason": "contract_not_active"}
    if view.dispute_open:
        return {"reason": "dispute_open"}
    if view.is_duplicate:
        return {"reason": "requires_human_review", "flag": "duplicate_charge"}
    if view.billed_after_cancellation:
        return {"reason": "requires_human_review", "flag": "billed_after_cancellation"}
    if not view.in_window:
        return {"reason": "outside_refund_window"}
    if amount > view.refundable_remaining_usd:
        return {"reason": "over_remaining_amount", "remaining_usd": view.refundable_remaining_usd}
    limit = REFUND_LIMITS_USD[account.tier]
    if view.refunded_usd + amount > limit:
        return {"reason": "over_tier_limit", "limit_usd": limit, "already_refunded_usd": view.refunded_usd}
    if _recent_agent_refund(ledger, account.user_id, today):
        return {"reason": "refund_frequency_limit"}
    return None


def issue_refund(*, user_id: str, charge_id: str, amount_usd: float, reason: str, idempotency_key: str,
                 records: BillingRecords, ledger: RefundLedger, today: date) -> ToolResult:
    if amount_usd <= 0:
        raise ToolError("Refund amount must be positive", retryable=False)
    account = _require_account(user_id)

    previous = ledger.find_by_key(idempotency_key)
    if previous is not None and previous.user_id == user_id and previous.charge_id == charge_id:
        return ToolResult(ok=True, data={**refund_as_dict(previous), "replayed": True})

    view = find_charge_view(user_id, charge_id, records, ledger, today)
    block = _refund_block(account, view, round(amount_usd, 2), ledger, today)
    if block is not None:
        return ToolResult(ok=False, data=block)

    refund = Refund(
        refund_id=_new_id("rf"), charge_id=charge_id, user_id=user_id, amount_usd=round(amount_usd, 2),
        reason=reason, kind="agent", status="pending", created_at=today, reference=None,
        failure_reason=None, idempotency_key=idempotency_key,
    )
    ledger.add(refund)
    return ToolResult(ok=True, data={**refund_as_dict(refund), "replayed": False})


def create_ticket(store: TicketStore, *, user_id: str | None, summary: str, reason: str, priority: Priority,
                  issue_key: str, packet: dict[str, Any], today: date | None = None) -> ToolResult:
    """One open ticket per issue. Asking again returns the ticket that already exists."""
    if not summary.strip():
        raise ToolError("Ticket summary is required", retryable=False)
    existing = store.find_open(issue_key)
    if existing is not None:
        return ToolResult(ok=True, data={**existing.as_dict(), "existing": True})

    ticket = Ticket(
        ticket_id=_new_id("tk"), user_id=user_id, summary=summary.strip(), reason=reason, priority=priority,
        issue_key=issue_key, status="open", created_at=today or date.today(),
        packet=MappingProxyType(dict(packet)),
    )
    store.save(ticket)
    return ToolResult(ok=True, data={**ticket.as_dict(), "existing": False})


def approve_refund(store: TicketStore, ledger: RefundLedger, records: BillingRecords, *, ticket_id: str,
                   approver: str, note: str, charge_id: str, amount_usd: float, today: date) -> ToolResult:
    """Human reviewer only. May exceed the tier limit, never the charge. Not registered as a model tool."""
    if not approver.strip() or not note.strip():
        raise ToolError("Approver and note are required for a human approval", retryable=False)
    ticket = store.get(ticket_id)
    if ticket is None or ticket.status != "open" or ticket.user_id is None:
        return ToolResult(ok=False, data={"reason": "ticket_not_open"})

    view = find_charge_view(ticket.user_id, charge_id, records, ledger, today)
    if view is None:
        return ToolResult(ok=False, data={"reason": "charge_not_found"})
    if amount_usd <= 0 or amount_usd > view.refundable_remaining_usd:
        return ToolResult(ok=False, data={"reason": "over_remaining_amount",
                                          "remaining_usd": view.refundable_remaining_usd})

    refund = Refund(
        refund_id=_new_id("rf"), charge_id=charge_id, user_id=ticket.user_id, amount_usd=round(amount_usd, 2),
        reason=f"Approved by {approver.strip()}: {note.strip()}", kind="human_approved", status="pending",
        created_at=today, reference=None, failure_reason=None, idempotency_key=f"{ticket_id}:{charge_id}",
    )
    ledger.add(refund)
    store.save(replace(ticket, status="resolved"))
    return ToolResult(ok=True, data=refund_as_dict(refund))
