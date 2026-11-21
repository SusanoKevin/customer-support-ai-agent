"""End-to-end turns through the state machine with a scripted model, a fake retriever, and seed billing data.

Scenario ids refer to docs/test_scenarios.md. No test calls Gemini or the database.
"""

import random
from dataclasses import replace
from datetime import date

from app.agent import templates
from app.agent.deps import Deps
from app.agent.llm import Classification, LLMError, LLMReply, Usage
from app.agent.nodes import match_charge, refund_reason
from app.agent.orchestrator import run_turn
from app.agent.pricing import cost_usd
from app.agent.sessions import InMemorySessionStore
from app.config import Settings
from app.events import (
    DoneEvent, ErrorEvent, EscalationEvent, Event, StatusEvent, TokenEvent, ToolEvent, TraceEvent,
)
from app.rag.retriever import Chunk
from app.tools.billing import load_billing
from app.tools.stores import InMemoryRefundLedger, InMemoryTicketStore

TODAY = date(2026, 11, 19)
MAYA = {"email": "maya@example.com", "last4": "4242"}
DEV = {"email": "dev@example.com", "last4": "1881"}
LEE = {"email": "lee@example.com", "last4": "5150"}
ANSWER = "Here is what I found [refunds:1:0]."
CLASSIFY_USAGE = Usage(model="gemini-3.5-flash-lite", tokens_in=300, tokens_out=40)
ANSWER_USAGE = Usage(model="gemini-3.8-flash", tokens_in=900, tokens_out=120)


def _chunk(chunk_id: str, similarity: float = 0.72) -> Chunk:
    return Chunk(chunk_id=chunk_id, doc=chunk_id.split(":")[0], heading="h", text="policy text",
                 tiers=("free", "pro", "enterprise"), similarity=similarity)


class FakeRetriever:
    def __init__(self, similarity: float = 0.72) -> None:
        self.similarity = similarity
        self.tiers: list[str | None] = []

    async def search(self, query: str, tier: str | None, top_k: int) -> list[Chunk]:
        self.tiers.append(tier)
        return [_chunk("refunds:1:0", self.similarity), _chunk("refunds:0:0", self.similarity - 0.02)]


class FakeLLM:
    def __init__(self, script: list[Classification], answers: list[str] | None = None,
                 classify_error: LLMError | None = None) -> None:
        self.script = list(script)
        self.answers = list(answers or [])
        self.classify_error = classify_error

    async def classify(self, message: str, recent_turns: str) -> LLMReply[Classification]:
        if self.classify_error is not None:
            raise self.classify_error
        return LLMReply(self.script.pop(0), CLASSIFY_USAGE)

    async def generate(self, system: str, prompt: str) -> LLMReply[str]:
        return LLMReply(self.answers.pop(0) if self.answers else ANSWER, ANSWER_USAGE)


def C(intent: str, **fields) -> Classification:
    return Classification(intent=intent, search_query=fields.pop("search_query", "refund policy"), **fields)


def make_deps(*script: Classification, answers=None, failure_rate=0.0, retriever=None, classify_error=None) -> Deps:
    records = load_billing()
    return Deps(
        llm=FakeLLM(list(script), answers, classify_error), retriever=retriever or FakeRetriever(), records=records,
        ledger=InMemoryRefundLedger(records.refunds), tickets=InMemoryTicketStore(), sessions=InMemorySessionStore(),
        settings=Settings(_env_file=None, simulate_tool_failure_rate=failure_rate),
        today=lambda: TODAY, rng=random.Random(0), retry_delay_s=0,
    )


async def turn(deps: Deps, sid: str = "session-0001") -> list[Event]:
    events = [e async for e in run_turn(sid, "customer message", deps)]
    assert isinstance(events[-1], DoneEvent)  # G6
    return events


def tools(events: list[Event]) -> list[str]:
    return [e.name for e in events if isinstance(e, ToolEvent)]


def tool(events: list[Event], name: str) -> ToolEvent:
    return next(e for e in events if isinstance(e, ToolEvent) and e.name == name)


def escalation(events: list[Event]) -> EscalationEvent | None:
    return next((e for e in events if isinstance(e, EscalationEvent)), None)


def text(events: list[Event]) -> str:
    return "".join(e.text for e in events if isinstance(e, TokenEvent))


def agent_refunds(deps: Deps, user_id: str = "u_1001") -> list:
    return [r for r in deps.ledger.refunds_for(user_id) if r.kind == "agent"]


# --- refunds ----------------------------------------------------------------

async def test_pro_refund_within_limit_runs_the_full_tool_chain():  # S1.1
    deps = make_deps(C("refund_request", amount_usd=30, **MAYA))
    events = await turn(deps)
    assert tools(events) == ["verify_account", "retrieve_policy", "lookup_charges", "issue_refund"]
    refund = tool(events, "issue_refund")
    assert refund.ok
    assert text(events) == templates.refund_issued(30.0, "in_m1", refund.output["refund_id"], replayed=False)
    assert [r.amount_usd for r in agent_refunds(deps)] == [30.0]
    assert escalation(events) is None


async def test_request_waits_for_identity_then_continues():  # S1.1, identity given second
    deps = make_deps(C("refund_request", amount_usd=30), C("provide_identity", **MAYA))
    first = await turn(deps)
    assert text(first) == templates.ASK_IDENTITY and tools(first) == []
    second = await turn(deps)
    assert tool(second, "issue_refund").ok


async def test_over_limit_becomes_a_normal_priority_ticket():  # S1.2
    deps = make_deps(C("refund_request", amount_usd=80, **MAYA))
    events = await turn(deps)
    esc = escalation(events)
    assert (esc.reason, esc.priority) == ("over_tier_limit", "normal")
    assert esc.ticket_id in text(events)
    assert agent_refunds(deps) == []


async def test_injected_500_refund_is_declined_against_the_charge():  # S8.1
    deps = make_deps(C("refund_request", amount_usd=500, **MAYA))
    events = await turn(deps)
    assert tool(events, "issue_refund").output["reason"] == "over_remaining_amount"
    assert agent_refunds(deps) == []  # G1


async def test_claimed_enterprise_tier_still_gets_the_pro_limit():  # S8.2
    deps = make_deps(C("refund_request", amount_usd=70, **MAYA))
    events = await turn(deps)
    assert tool(events, "issue_refund").output["limit_usd"] == 50.0
    assert escalation(events).reason == "over_tier_limit"
    assert agent_refunds(deps) == []


async def test_split_request_is_caught_on_the_second_turn():  # S8.3
    deps = make_deps(C("refund_request", amount_usd=40, **MAYA), C("refund_request", amount_usd=40))
    assert tool(await turn(deps), "issue_refund").ok
    second = await turn(deps)
    assert escalation(second).reason == "over_tier_limit"
    assert len(agent_refunds(deps)) == 1


async def test_charge_outside_window_goes_to_review():  # S3.2
    deps = make_deps(C("refund_request", amount_usd=20, charge_ref="October", **MAYA))
    assert escalation(await turn(deps)).reason == "outside_refund_window"


async def test_unknown_invoice_lists_only_the_customers_own_charges():  # S4.1
    deps = make_deps(C("refund_request", amount_usd=20, charge_ref="in_d1", **MAYA))
    reply = text(await turn(deps))
    assert "in_m1" in reply
    assert "in_d1" not in reply and "in_d2" not in reply


# --- billing disputes -------------------------------------------------------

async def test_verified_duplicate_is_escalated_without_refunding():  # S2.1b
    deps = make_deps(C("billing_dispute", **DEV))
    events = await turn(deps)
    esc = escalation(events)
    assert (esc.reason, esc.priority) == ("duplicate_charge", "high")
    assert "issue_refund" not in tools(events)


async def test_customer_insisting_against_records_escalates_on_second_pushback():  # S2.2
    deps = make_deps(C("billing_dispute", **MAYA),
                     C("billing_dispute", disputes_previous_answer=True),
                     C("billing_dispute", disputes_previous_answer=True))
    assert escalation(await turn(deps)) is None
    assert escalation(await turn(deps)) is None
    third = await turn(deps)
    assert escalation(third).reason == "charge_dispute_unresolved"
    assert agent_refunds(deps) == []


# --- refund status ----------------------------------------------------------

async def test_recent_refund_is_explained_not_reissued():  # S6.1
    deps = make_deps(C("refund_status", **MAYA))
    events = await turn(deps)
    assert "get_refund_status" in tools(events)
    assert escalation(events) is None
    assert agent_refunds(deps) == []


async def test_failed_refund_goes_to_a_person():  # S6.3
    deps = make_deps(C("refund_status", **DEV))
    esc = escalation(await turn(deps))
    assert (esc.reason, esc.priority) == ("refund_failed", "high")


# --- identity and account state ---------------------------------------------

async def test_three_failed_verifications_escalate_and_mask_digits():  # S7.1
    wrong = [C("refund_request", email="maya@example.com", last4=d) for d in ("1111", "2222", "3333")]
    deps = make_deps(*wrong)
    first = await turn(deps)
    assert text(first) == templates.IDENTITY_NOT_VERIFIED
    assert tool(first, "verify_account").input["last4"] == "****"
    await turn(deps)
    third = await turn(deps)
    assert escalation(third).reason == "identity_not_verified"
    assert "issue_refund" not in tools(third)


async def test_suspended_contract_routes_to_a_person():  # S7.2
    deps = make_deps(C("refund_request", amount_usd=20, **LEE))
    events = await turn(deps)
    assert escalation(events).reason == "contract_not_active"
    assert "issue_refund" not in tools(events)


# --- human handoff ----------------------------------------------------------

async def test_asking_for_a_person_escalates_immediately():  # S9.1
    deps = make_deps(C("wants_human"))
    events = await turn(deps)
    assert escalation(events).reason == "customer_requested_human"
    assert tools(events) == ["create_ticket"]


async def test_open_ticket_blocks_refund_actions_but_not_questions():  # S9.2, S9.3
    deps = make_deps(C("refund_request", amount_usd=80, **MAYA),
                     C("refund_request", amount_usd=50),
                     C("policy_question", search_query="seats"))
    ticket_id = escalation(await turn(deps)).ticket_id
    blocked = await turn(deps)
    assert text(blocked) == templates.awaiting_human(ticket_id)
    assert tools(blocked) == []
    question = await turn(deps)
    assert text(question) == ANSWER


# --- guardrails and failures ------------------------------------------------

async def test_uncited_answer_is_regenerated_once_then_escalated():
    deps = make_deps(C("policy_question"), answers=["No citation here.", "Still none."])
    events = await turn(deps)
    assert escalation(events).reason == "uncited_answer"
    assert "No citation" not in text(events)


async def test_uncited_first_draft_is_replaced_by_a_cited_one():
    deps = make_deps(C("policy_question"), answers=["No citation here.", ANSWER])
    assert text(await turn(deps)) == ANSWER


async def test_low_retrieval_confidence_escalates():
    deps = make_deps(C("policy_question"), retriever=FakeRetriever(similarity=0.4))
    assert escalation(await turn(deps)).reason == "low_retrieval_confidence"


async def test_unverified_questions_search_every_tier():
    deps = make_deps(C("policy_question"))
    await turn(deps)
    assert deps.retriever.tiers == [None]


async def test_out_of_scope_gets_a_fixed_reply_and_no_ticket():
    deps = make_deps(C("out_of_scope"))
    events = await turn(deps)
    assert text(events) == templates.OUT_OF_SCOPE
    assert escalation(events) is None and tools(events) == []


async def test_tool_outage_escalates_and_never_claims_a_refund():  # S10.2
    deps = make_deps(C("refund_request", amount_usd=30, **MAYA), failure_rate=1.0)
    events = await turn(deps)
    assert any(isinstance(e, ErrorEvent) and e.retryable for e in events)
    assert escalation(events).reason == "tool_failure"
    assert "refunded" not in text(events).lower()
    assert agent_refunds(deps) == []


async def test_model_rate_limit_ends_the_turn_cleanly():  # S10.5
    deps = make_deps(classify_error=LLMError("429", retryable=True, code="rate_limited"))
    events = await turn(deps)
    assert any(isinstance(e, ErrorEvent) and e.code == "rate_limited" for e in events)
    assert text(events) == templates.MODEL_UNAVAILABLE


async def test_every_started_step_completes_or_fails():
    deps = make_deps(C("refund_request", amount_usd=30, **MAYA))
    events = await turn(deps)
    started = [e.step for e in events if isinstance(e, StatusEvent) and e.state == "started"]
    finished = [e.step for e in events if isinstance(e, StatusEvent) and e.state in ("completed", "failed")
                and e.step in started]
    assert started == finished


# --- observability ----------------------------------------------------------

def traces(events: list[Event]) -> dict[str, TraceEvent]:
    return {e.step: e for e in events if isinstance(e, TraceEvent)}


async def test_model_steps_report_model_tokens_and_cost():
    events = await turn(make_deps(C("policy_question")))
    rows = traces(events)
    assert (rows["classify_intent"].model, rows["classify_intent"].tokens_in) == ("gemini-3.5-flash-lite", 300)
    assert rows["respond"].model == "gemini-3.8-flash"
    assert rows["respond"].cost_usd == round(cost_usd(ANSWER_USAGE), 6)
    assert rows["retrieve_policy"].model is None and rows["retrieve_policy"].tokens_in == 0


async def test_regenerated_answer_counts_both_model_calls():
    events = await turn(make_deps(C("policy_question"), answers=["No citation here.", ANSWER]))
    respond = traces(events)["respond"]
    assert (respond.tokens_in, respond.tokens_out) == (1800, 240)


async def test_failed_model_step_still_reports_latency():
    deps = make_deps(classify_error=LLMError("503", retryable=True, code="model_unavailable"))
    assert "classify_intent" in traces(await turn(deps))


async def test_refund_reason_is_the_customers_words_not_the_search_query():
    deps = make_deps(C("refund_request", amount_usd=30, search_query="refund policy invoice", **MAYA))
    events = await turn(deps)
    assert tool(events, "issue_refund").input["reason"] == "customer message"


def test_refund_reason_masks_email_and_card_digits():
    reason = refund_reason("Refund $30 please. maya@example.com, last 4 is 4242")
    assert "maya@example.com" not in reason and "4242" not in reason
    assert reason.startswith("Refund $30 please.")


def test_refund_reason_falls_back_when_the_message_says_nothing():
    assert refund_reason("yes") == "Customer confirmed the refund request"


# --- found in the live sweep (scripts/live_eval.py, 2026-11-20) -------------

async def test_digit_only_retries_reuse_the_email_and_count_toward_the_limit():  # S7.1 live
    deps = make_deps(C("refund_request", email="maya@example.com", last4="1111"),
                     C("provide_identity", last4="2222"), C("provide_identity", last4="3333"))
    await turn(deps)
    second = await turn(deps)
    assert tools(second) == ["verify_account"]
    third = await turn(deps)
    assert escalation(third).reason == "identity_not_verified"


async def test_request_without_amount_on_an_old_charge_goes_to_review():  # S4.3 live
    deps = make_deps(C("refund_request", charge_ref="October", **MAYA))
    events = await turn(deps)
    assert escalation(events).reason == "outside_refund_window"
    assert "issue_refund" not in tools(events)


async def test_follow_up_amount_applies_to_the_charge_under_discussion():  # S4.3 live, charge drift
    deps = make_deps(C("refund_request", charge_ref="in_d1", **DEV), C("refund_request", amount_usd=100))
    first = await turn(deps)
    assert "How much" in text(first)
    second = await turn(deps)
    assert tool(second, "issue_refund").input["charge_id"] == "ch_d1"


# --- review findings (log B1 to B6) ----------------------------------------

class AnswerModelDownOnce(FakeLLM):
    """First answer call fails as if 3.8 Flash were busy and Lite rate limited (D27)."""

    def __init__(self, script: list[Classification]) -> None:
        super().__init__(script)
        self.has_failed = False

    async def generate(self, system: str, prompt: str) -> LLMReply[str]:
        if not self.has_failed:
            self.has_failed = True
            raise LLMError("busy", retryable=True, code="rate_limited")
        return await super().generate(system, prompt)


def with_llm(deps: Deps, llm) -> Deps:
    return replace(deps, llm=llm)


async def test_refund_is_confirmed_with_fixed_text_even_when_the_answer_model_is_down():  # B1
    deps = make_deps(C("refund_request", amount_usd=30, **MAYA))
    deps = with_llm(deps, AnswerModelDownOnce(deps.llm.script))
    events = await turn(deps)
    refund = tool(events, "issue_refund")
    assert refund.ok
    reply = text(events)
    assert reply != templates.MODEL_UNAVAILABLE
    assert "$30.00" in reply and refund.output["refund_id"] in reply and "in_m1" in reply
    assert "5 to 10 business days" in reply
    assert not any(isinstance(e, ErrorEvent) for e in events)


async def test_no_verification_after_the_lockout():  # B5
    wrong = [C("provide_identity", email="maya@example.com", last4=d) for d in ("1111", "2222", "3333")]
    deps = make_deps(*wrong, C("provide_identity", **MAYA))
    for _ in range(3):
        await turn(deps)
    locked = await turn(deps)
    assert tools(locked) == []
    assert text(locked) == templates.IDENTITY_LOCKED
    assert deps.sessions.get("session-0001").account is None


class BrokenRetriever(FakeRetriever):
    async def search(self, query: str, tier: str | None, top_k: int) -> list[Chunk]:
        raise RuntimeError("embed_content 429 RESOURCE_EXHAUSTED")


async def test_retrieval_outage_retries_then_escalates():  # B2
    deps = make_deps(C("policy_question"), retriever=BrokenRetriever())
    events = await turn(deps)
    assert escalation(events).reason == "tool_failure"
    assert "RESOURCE_EXHAUSTED" not in tool(events, "retrieve_policy").output["error"]
    assert deps.sessions.get("session-0001") is not None  # the turn was saved


async def test_tool_outage_marks_the_step_failed_and_keeps_the_retry_separate():  # B4
    deps = make_deps(C("refund_request", amount_usd=30, **MAYA), failure_rate=1.0)
    events = await turn(deps)
    rows = [(e.step, e.state) for e in events if isinstance(e, StatusEvent) and e.step.startswith("verify_account")]
    assert rows == [("verify_account", "started"), ("verify_account_retry", "failed"), ("verify_account", "failed")]


CHARGES = [{"charge_id": "ch_nov", "invoice_id": "in_n", "invoice_period": "2026-11"},
           {"charge_id": "ch_oct", "invoice_id": "in_o", "invoice_period": "2026-10"},
           {"charge_id": "ch_may", "invoice_id": "in_y", "invoice_period": "2026-05"}]


def test_match_charge_reads_month_names_and_abbreviations():  # B6 keeps these working
    assert match_charge("October", CHARGES)["charge_id"] == "ch_oct"
    assert match_charge("oct", CHARGES)["charge_id"] == "ch_oct"
    assert match_charge("my May invoice", CHARGES)["charge_id"] == "ch_may"
    assert match_charge("last month", CHARGES)["charge_id"] == "ch_oct"
    assert match_charge("IN_N", CHARGES)["charge_id"] == "ch_nov"
    assert match_charge(None, CHARGES)["charge_id"] == "ch_nov"


def test_month_words_inside_other_words_do_not_match():  # B6
    assert match_charge("maybe the big one", CHARGES) is None
    assert match_charge("decline fee", CHARGES) is None
    assert match_charge("octopus", CHARGES) is None


def test_replayed_refund_is_confirmed_as_already_issued():  # B1, idempotent retry of the same request
    text_ = templates.refund_issued(30.0, "in_m1", "rf_1", replayed=True)
    assert text_.startswith("That refund was already issued") and "rf_1" in text_
