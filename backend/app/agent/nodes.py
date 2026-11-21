"""One function per state machine node. Each takes a state and returns a new state plus events.

The model labels the message (classify_intent) and writes grounded answers (respond).
Every routing and escalation decision below is plain code.
"""

import re
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Any

from app.agent import templates
from app.agent.deps import Deps
from app.agent.guardrails import grounding_gate, retrieval_gate
from app.agent.llm import Usage
from app.agent.state import (
    ACCOUNT_INTENTS, ACTION_INTENTS, MAX_DISPUTES, MAX_IDENTITY_ATTEMPTS, AgentState, Node, recent_turns,
)
from app.agent.tool_runner import ToolCall, run_tool
from app.events import EscalationEvent, Event, TokenEvent
from app.rag.retriever import Chunk
from app.tools.accounts import find_account, verify_account
from app.tools.actions import create_ticket, issue_refund, ticket_priority
from app.tools.billing import get_refund_status, lookup_charges
from app.tools.policies import retrieve_policy

SETTLEMENT_BUSINESS_DAYS = 10
TOKEN_CHUNK_WORDS = 4
REFUND_REASON_MAX_CHARS = 280
REFUND_REASON_MIN_CHARS = 12  # shorter messages ("yes", "do it") say nothing a reviewer can use
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
DIGIT_RUN = re.compile(r"\b\d{4,}\b")
# Declines that policy routes to a person rather than explaining and moving on.
ESCALATE_ON_DECLINE = {
    "over_tier_limit": "over_tier_limit",
    "outside_refund_window": "outside_refund_window",
    "refund_frequency_limit": "refund_frequency_limit",
    "dispute_open": "open_dispute",
    "contract_not_active": "contract_not_active",
}
MONTHS = {m: f"{i:02d}" for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"], start=1)}
# A month's full name or abbreviation as a whole word: "October", "oct", "sept". Not "maybe" (log B6).
MONTH_WORD = re.compile(r"\b(" + "|".join([*MONTHS, *(m[:3] for m in MONTHS), "sept"]) + r")\b")


@dataclass(frozen=True)
class Step:
    state: AgentState
    events: tuple[Event, ...] = ()
    usage: tuple[Usage, ...] = ()  # one entry per model call this step made


def _to(state: AgentState, node: Node, **changes: Any) -> AgentState:
    return replace(state, node=node, **changes)


def _reply(state: AgentState, text: str, **changes: Any) -> AgentState:
    return replace(state, node=Node.RESPOND, reply=text, **changes)


def _escalate(state: AgentState, reason: str, **changes: Any) -> AgentState:
    return replace(state, node=Node.ESCALATE, escalation_reason=reason, **changes)


async def _tool(deps: Deps, name: str, fn: Any, kwargs: dict[str, Any]) -> ToolCall:
    return await run_tool(name, fn, kwargs, failure_rate=deps.settings.simulate_tool_failure_rate,
                          rng=deps.rng, retry_delay_s=deps.retry_delay_s)


# --- classify_intent --------------------------------------------------------

async def classify_intent(state: AgentState, deps: Deps) -> Step:
    reply = await deps.llm.classify(state.user_message, recent_turns(state))
    c = reply.value
    pushed_back = c.disputes_previous_answer and state.last_was_refusal
    state = replace(state, classification=c, dispute_count=state.dispute_count + int(pushed_back))
    return Step(_route(_refresh_mode(state, deps), deps), usage=(reply.usage,))


def _refresh_mode(state: AgentState, deps: Deps) -> AgentState:
    """Back to normal once a human has resolved the open ticket."""
    if state.mode != "awaiting_human" or state.open_ticket_id is None:
        return state
    ticket = deps.tickets.get(state.open_ticket_id)
    return state if ticket is not None and ticket.status == "open" else replace(state, mode="bot", open_ticket_id=None)


def _route(state: AgentState, deps: Deps) -> AgentState:
    intent = state.intent
    # Refund status stays open: it only reads the ledger (review M1).
    if state.mode == "awaiting_human" and intent in ACTION_INTENTS | {"wants_human"}:
        return _reply(state, templates.awaiting_human(state.open_ticket_id))
    if intent == "wants_human":
        return _escalate(state, "customer_requested_human")
    if intent == "security_or_legal":
        return _escalate(state, "security_or_legal")
    if intent == "out_of_scope":
        return _reply(state, templates.OUT_OF_SCOPE)
    if intent == "other":
        return _reply(state, templates.GREETING)
    if intent == "provide_identity":
        return _to(state, Node.VERIFY_ACCOUNT) if state.account is None else _reply(state, templates.ALREADY_VERIFIED)
    if intent in ACCOUNT_INTENTS and state.account is None:
        return _to(state, Node.VERIFY_ACCOUNT)
    return _to(state, Node.RETRIEVE_POLICY)


# --- verify_account ---------------------------------------------------------

async def verify_account_node(state: AgentState, deps: Deps) -> Step:
    # The lockout must stop the check itself, or a 4-digit code can be guessed in one session (log B5).
    if state.identity_failures >= MAX_IDENTITY_ATTEMPTS:
        return Step(_reply(state, templates.IDENTITY_LOCKED, pending=None))
    c = state.classification
    request = state.pending if c.intent == "provide_identity" else c
    # "Try 2222" on a retry: the classifier only reads the latest message, so reuse the email already given.
    email = c.email or (state.last_email if c.last4 else None)
    if not (email and c.last4 and "@" in email):
        return Step(_reply(state, templates.ASK_IDENTITY, pending=request))

    email_key = email.strip().lower()
    if deps.email_failures.check(email_key) is not None:  # log P16: checked before the tool, so no guess is tested
        return Step(_reply(state, templates.EMAIL_LOCKED, pending=None))

    call = await _tool(deps, "verify_account", verify_account, {"email": email, "last4": c.last4})
    state = replace(state.logged(call.log_entry), last_email=email)
    if call.error is not None:
        return Step(_escalate(state, "tool_failure"), call.events)
    if not call.result.ok:
        deps.email_failures.add(email_key)
        failures = state.identity_failures + 1
        if failures >= MAX_IDENTITY_ATTEMPTS:
            return Step(_escalate(state, "identity_not_verified", identity_failures=failures, pending=None), call.events)
        return Step(_reply(state, templates.IDENTITY_NOT_VERIFIED, identity_failures=failures, pending=request),
                    call.events)

    account = find_account(call.result.data["user_id"])
    state = replace(state, account=account, identity_failures=0, pending=None)
    if request is None or request.intent == "provide_identity":
        return Step(_reply(state, templates.verified(account.name)), call.events)
    return Step(_to(state, Node.RETRIEVE_POLICY, classification=request), call.events)


# --- retrieve_policy --------------------------------------------------------

def _chunk(row: dict[str, Any]) -> Chunk:
    return Chunk(**{**row, "tiers": tuple(row["tiers"])})


async def retrieve_policy_node(state: AgentState, deps: Deps) -> Step:
    query = state.classification.search_query or state.user_message
    tier = state.account.tier if state.account else None
    call = await _tool(deps, "retrieve_policy", retrieve_policy,
                       {"retriever": deps.retriever, "query": query, "tier": tier})
    state = state.logged(call.log_entry)
    if call.error is not None:
        return Step(_escalate(state, "tool_failure"), call.events)

    state = replace(state, chunks=tuple(_chunk(row) for row in call.result.data["chunks"]))
    gate = retrieval_gate(list(state.chunks), deps.settings.rag_min_similarity, deps.settings.rag_min_chunks)
    if not gate.passed:
        return Step(_escalate(state, gate.reason), call.events)
    nxt = Node.DECIDE_ACTION if state.intent in ACCOUNT_INTENTS else Node.RESPOND
    return Step(_to(state, nxt), call.events)


# --- decide_action ----------------------------------------------------------

def match_charge(ref: str | None, charges: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Charges arrive newest first. No reference means the latest charge."""
    if not charges:
        return None
    if not ref:
        return charges[0]
    r = ref.strip().lower()
    exact = next((c for c in charges if r in (c["charge_id"].lower(), c["invoice_id"].lower(), c["invoice_period"])), None)
    if exact is not None:
        return exact
    if any(word in r for word in ("this month", "latest", "current", "recent")):
        return charges[0]
    if any(word in r for word in ("last month", "previous")):
        return charges[1] if len(charges) > 1 else charges[0]
    word = MONTH_WORD.search(r)
    if word is None:
        return None
    month = next(num for name, num in MONTHS.items() if name.startswith(word.group(1)[:3]))
    return next((c for c in charges if c["invoice_period"].endswith(f"-{month}")), None)


async def decide_action(state: AgentState, deps: Deps) -> Step:
    if state.intent == "refund_status":
        return await _refund_status(state, deps)
    if not state.account.can_take_actions:
        return Step(_escalate(state, "contract_not_active"))

    call = await _tool(deps, "lookup_charges", lookup_charges, {
        "user_id": state.account.user_id, "records": deps.records, "ledger": deps.ledger, "today": deps.today()})
    state = state.logged(call.log_entry)
    if call.error is not None:
        return Step(_escalate(state, "tool_failure"), call.events)
    charges = call.result.data["charges"]
    state = state.with_fact("charges", charges)
    nxt = _billing_dispute(state, charges) if state.intent == "billing_dispute" else _refund_request(state, charges)
    return Step(nxt, call.events)


def _billing_dispute(state: AgentState, charges: list[dict[str, Any]]) -> AgentState:
    duplicate = next((c for c in charges if c["is_duplicate"]), None)
    if duplicate is not None:
        return _escalate(state, "duplicate_charge", target_charge_id=duplicate["charge_id"])
    late = next((c for c in charges if c["billed_after_cancellation"]), None)
    if late is not None:
        return _escalate(state, "billed_after_cancellation", target_charge_id=late["charge_id"])
    if state.dispute_count >= MAX_DISPUTES:
        return _escalate(state, "charge_dispute_unresolved")
    return _to(state, Node.RESPOND, last_was_refusal=True)


def _refund_request(state: AgentState, charges: list[dict[str, Any]]) -> AgentState:
    c = state.classification
    focused = next((ch for ch in charges if ch["charge_id"] == state.focus_charge_id), None)
    target = focused if not c.charge_ref and focused is not None else match_charge(c.charge_ref, charges)
    if target is None:
        if state.dispute_count >= MAX_DISPUTES:
            return _escalate(state, "charge_dispute_unresolved")
        return _reply(state, templates.charge_not_found(charges), last_was_refusal=True)
    state = replace(state, focus_charge_id=target["charge_id"], target_charge_id=target["charge_id"])
    if not c.amount_usd:
        # Asking for an amount the window guard would refuse anyway only stalls the customer (live sweep, S4.3).
        if not target["in_refund_window"]:
            return _escalate(state, "outside_refund_window")
        return _reply(state, templates.ask_amount(target))
    return _to(state, Node.ISSUE_REFUND)


def business_days_between(start: date, end: date) -> int:
    days, current = 0, start
    while current < end:
        current += timedelta(days=1)
        days += current.weekday() < 5
    return days


async def _refund_status(state: AgentState, deps: Deps) -> Step:
    call = await _tool(deps, "get_refund_status", get_refund_status,
                       {"user_id": state.account.user_id, "ledger": deps.ledger})
    state = state.logged(call.log_entry)
    if call.error is not None:
        return Step(_escalate(state, "tool_failure"), call.events)
    refunds = call.result.data["refunds"]
    state = state.with_fact("refunds", refunds)
    if not refunds:
        return Step(_to(state, Node.RESPOND, last_was_refusal=True), call.events)

    latest = refunds[0]
    waited = business_days_between(date.fromisoformat(latest["created_at"]), deps.today())
    state = replace(state.with_fact("business_days_since_latest_refund", waited), target_charge_id=latest["charge_id"])
    if latest["status"] == "failed":
        return Step(_escalate(state, "refund_failed"), call.events)
    overdue = latest["status"] == "succeeded" and waited > SETTLEMENT_BUSINESS_DAYS and state.dispute_count >= 1
    if overdue or state.dispute_count >= MAX_DISPUTES:
        return Step(_escalate(state, "refund_not_received"), call.events)
    return Step(_to(state, Node.RESPOND, last_was_refusal=True), call.events)


# --- issue_refund -----------------------------------------------------------

def refund_reason(message: str) -> str:
    """The customer's own words for the human reviewer, with email and card digits masked (log F6)."""
    masked = DIGIT_RUN.sub("****", EMAIL.sub("[email]", message)).strip()
    if len(masked) < REFUND_REASON_MIN_CHARS:
        return "Customer confirmed the refund request"
    return masked[:REFUND_REASON_MAX_CHARS]


async def issue_refund_node(state: AgentState, deps: Deps) -> Step:
    amount = round(state.classification.amount_usd, 2)
    call = await _tool(deps, "issue_refund", issue_refund, {
        "user_id": state.account.user_id, "charge_id": state.target_charge_id, "amount_usd": amount,
        "reason": refund_reason(state.user_message),
        "idempotency_key": f"{state.session_id}:{state.turn}:{state.target_charge_id}:{amount}",
        "records": deps.records, "ledger": deps.ledger, "today": deps.today(),
    })
    state = state.logged(call.log_entry)
    if call.error is not None:
        return Step(_escalate(state.with_fact("refund", "not confirmed"), "tool_failure"), call.events)
    data = call.result.data
    if call.result.ok:
        text = templates.refund_issued(data["amount_usd"], _invoice_id(state, data["charge_id"]), data["refund_id"],
                                       data["replayed"])
        return Step(_reply(state.with_fact("refund_issued", data), text, dispute_count=0, last_was_refusal=False),
                    call.events)
    return Step(_after_decline(state.with_fact("refund_declined", data), data), call.events)


def _invoice_id(state: AgentState, charge_id: str) -> str:
    """Customers know invoice numbers, not internal charge ids."""
    charges = state.facts.get("charges", ())
    return next((c["invoice_id"] for c in charges if c["charge_id"] == charge_id), charge_id)


def _after_decline(state: AgentState, data: dict[str, Any]) -> AgentState:
    reason = data["reason"]
    if reason == "requires_human_review":
        return _escalate(state, data["flag"])
    if reason in ESCALATE_ON_DECLINE:
        return _escalate(state, ESCALATE_ON_DECLINE[reason])
    if state.dispute_count >= MAX_DISPUTES:
        return _escalate(state, "charge_dispute_unresolved")
    return _to(state, Node.RESPOND, last_was_refusal=True)


# --- escalate ---------------------------------------------------------------

def build_packet(state: AgentState, reason: str) -> dict[str, Any]:
    """Handoff packet built from state, so nothing in it is model-written."""
    a, c = state.account, state.classification
    customer = ({"user_id": a.user_id, "tier": a.tier, "contract_status": a.contract_status, "verified": True}
                if a else {"verified": False})
    return {
        "reason": reason,
        "customer": customer,
        "claim": {"message": state.user_message, "amount_usd": c.amount_usd if c else None,
                  "charge_ref": c.charge_ref if c else None},
        "charge_id": state.target_charge_id,
        "records_checked": dict(state.facts),
        "agent_actions": list(state.tool_log),
        "policies_cited": [ch.chunk_id for ch in state.chunks],
        "dispute_count": state.dispute_count,
        "session_id": state.session_id,
    }


async def escalate_node(state: AgentState, deps: Deps) -> Step:
    reason = state.escalation_reason or "max_steps"
    account = state.account
    tier = account.tier if account else None
    priority = ticket_priority(reason, tier)
    owner = account.user_id if account else state.session_id
    call = await _tool(deps, "create_ticket", create_ticket, {
        "store": deps.tickets, "user_id": account.user_id if account else None,
        "summary": f"{templates.TICKET_SUMMARIES.get(reason, reason)}: {state.user_message[:200]}",
        "reason": reason, "priority": priority, "issue_key": f"{owner}:{reason}:{state.target_charge_id or ''}",
        "packet": build_packet(state, reason), "today": deps.today(),
    })
    state = state.logged(call.log_entry)
    if call.error is not None:
        return Step(_reply(state, templates.TICKET_FAILED), call.events)

    ticket = call.result.data
    text = templates.escalated(reason, ticket["ticket_id"], tier, priority, ticket["existing"])
    events = (*call.events, EscalationEvent(reason=reason, ticket_id=ticket["ticket_id"], priority=priority))
    return Step(_reply(state, text, mode="awaiting_human", open_ticket_id=ticket["ticket_id"], dispute_count=0,
                       last_was_refusal=False), events)


# --- respond ----------------------------------------------------------------

def token_events(text: str) -> tuple[TokenEvent, ...]:
    words = text.split(" ")
    groups = [" ".join(words[i:i + TOKEN_CHUNK_WORDS]) for i in range(0, len(words), TOKEN_CHUNK_WORDS)]
    return tuple(TokenEvent(text=g + (" " if i < len(groups) - 1 else "")) for i, g in enumerate(groups))


async def _grounded_answer(state: AgentState, deps: Deps) -> tuple[str | None, tuple[Usage, ...]]:
    """Buffer the whole answer, check citations, regenerate once. Nothing unchecked reaches the customer.

    Returns the answer (None if both drafts failed the gate) and the usage of every call made."""
    a = state.account
    account = {"name": a.name, "tier": a.tier, "contract_status": a.contract_status} if a else None
    excerpts = "\n".join(f"[{c.chunk_id}] {c.heading}: {c.text}" for c in state.chunks)
    prompt = templates.answer_prompt(state.user_message, recent_turns(state), account, dict(state.facts), excerpts)
    usage: tuple[Usage, ...] = ()
    for _ in range(2):
        reply = await deps.llm.generate(templates.RESPOND_SYSTEM, prompt)
        usage = (*usage, reply.usage)
        if grounding_gate(reply.value, list(state.chunks)).passed:
            return reply.value, usage
    return None, usage


async def respond(state: AgentState, deps: Deps) -> Step:
    if state.reply is not None:
        return Step(_to(state, Node.END), token_events(state.reply))
    text, usage = await _grounded_answer(state, deps)
    if text is None:
        return Step(_escalate(state, "uncited_answer"), usage=usage)
    return Step(_to(state, Node.END, reply=text), token_events(text), usage)
