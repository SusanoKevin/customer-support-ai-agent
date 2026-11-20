"""Billing records and the guarded refund tools. Scenario ids refer to docs/test_scenarios.md."""

from dataclasses import replace
from datetime import date

import pytest

from app.tools.actions import approve_refund, create_ticket, issue_refund, ticket_priority
from app.tools.base import ToolError
from app.tools.billing import (
    BillingRecords,
    Charge,
    Dispute,
    PaymentMethod,
    Refund,
    Subscription,
    charge_views,
    get_refund_status,
    load_billing,
    lookup_charges,
)
from app.tools.registry import MODEL_TOOLS
from app.tools.stores import InMemoryRefundLedger, InMemoryTicketStore

TODAY = date(2026, 11, 19)
CARD = PaymentMethod(brand="visa", last4="4242", status="active")


def _charge(charge_id: str, user_id: str = "u_1001", amount: float = 87.0, billed: date = date(2026, 11, 5),
            period: str = "2026-11", description: str = "Pro, 3 seats") -> Charge:
    return Charge(charge_id=charge_id, user_id=user_id, invoice_id=f"in_{charge_id}", invoice_period=period,
                  amount_usd=amount, billed_at=billed, description=description, payment_method=CARD)


def _refund(refund_id: str, charge_id: str, amount: float, created: date, *, user_id: str = "u_1001",
            kind: str = "agent", status: str = "succeeded", key: str | None = None) -> Refund:
    return Refund(refund_id=refund_id, charge_id=charge_id, user_id=user_id, amount_usd=amount, reason="r",
                  kind=kind, status=status, created_at=created, reference=None, failure_reason=None,
                  idempotency_key=key)


def _records(*charges: Charge, disputes=(), subscriptions=()) -> BillingRecords:
    return BillingRecords(charges=charges, refunds=(), disputes=tuple(disputes), subscriptions=tuple(subscriptions))


def _refund_call(records, ledger, amount, *, user_id="u_1001", charge_id="ch_m1", key="k1"):
    return issue_refund(user_id=user_id, charge_id=charge_id, amount_usd=amount, reason="seat removed",
                        idempotency_key=key, records=records, ledger=ledger, today=TODAY)


# --- records and computed flags ---------------------------------------------

def test_seed_billing_file_loads_and_covers_demo_accounts():
    records = load_billing()
    owners = {c.user_id for c in records.charges}
    assert {"u_1001", "u_1002", "u_1004"} <= owners
    assert not any(c.user_id == "u_1003" for c in records.charges)  # Free tier has no paid charges


def test_later_of_two_identical_charges_is_flagged_duplicate():
    records = _records(_charge("ch_m1"), _charge("ch_m2"))
    views = {v.charge.charge_id: v for v in charge_views("u_1001", records, InMemoryRefundLedger(()), TODAY)}
    assert views["ch_m1"].is_duplicate is False
    assert views["ch_m2"].is_duplicate is True


def test_charge_after_cancellation_took_effect_is_flagged():
    sub = Subscription(user_id="u_1001", cancelled_at=date(2026, 10, 25), cancellation_effective_at=date(2026, 11, 4))
    records = _records(_charge("ch_m4"), subscriptions=[sub])
    [view] = charge_views("u_1001", records, InMemoryRefundLedger(()), TODAY)
    assert view.billed_after_cancellation is True


def test_lookup_charges_only_returns_the_callers_charges():
    records = _records(_charge("ch_m1"), _charge("ch_d1", user_id="u_1002"))
    result = lookup_charges("u_1001", records, InMemoryRefundLedger(()), TODAY)
    assert [c["charge_id"] for c in result.data["charges"]] == ["ch_m1"]
    assert result.data["charges"][0]["refundable_remaining_usd"] == 87.0


# --- issue_refund guards, in order ------------------------------------------

def test_refund_within_pro_limit_is_issued_and_recorded():  # S1.1
    ledger = InMemoryRefundLedger(())
    result = _refund_call(_records(_charge("ch_m1")), ledger, 30)
    assert result.ok
    assert result.data["status"] == "pending"
    assert len(ledger.refunds_for("u_1001")) == 1


def test_other_accounts_charge_reads_as_not_found():  # S4.1
    result = _refund_call(_records(_charge("ch_d1", user_id="u_1002")), InMemoryRefundLedger(()), 30, charge_id="ch_d1")
    assert result.data == {"reason": "charge_not_found"}


def test_refund_blocked_when_contract_not_active():  # S7.2
    records = _records(_charge("ch_l1", user_id="u_1004"))
    result = _refund_call(records, InMemoryRefundLedger(()), 20, user_id="u_1004", charge_id="ch_l1")
    assert result.data["reason"] == "contract_not_active"


def test_refund_blocked_while_bank_dispute_is_open():  # S5.3
    records = _records(_charge("ch_m1"), disputes=[Dispute(charge_id="ch_m1", status="open", opened_at=TODAY)])
    assert _refund_call(records, InMemoryRefundLedger(()), 30).data["reason"] == "dispute_open"


def test_verified_duplicate_requires_human_review():  # S2.1
    records = _records(_charge("ch_m1"), _charge("ch_m2"))
    result = _refund_call(records, InMemoryRefundLedger(()), 30, charge_id="ch_m2")
    assert result.data == {"reason": "requires_human_review", "flag": "duplicate_charge"}


def test_charge_after_cancellation_requires_human_review():  # S2.4
    sub = Subscription(user_id="u_1001", cancelled_at=date(2026, 10, 25), cancellation_effective_at=date(2026, 11, 4))
    records = _records(_charge("ch_m4"), subscriptions=[sub])
    result = _refund_call(records, InMemoryRefundLedger(()), 30, charge_id="ch_m4")
    assert result.data == {"reason": "requires_human_review", "flag": "billed_after_cancellation"}


def test_charge_older_than_30_days_is_outside_window():  # S3.2
    records = _records(_charge("ch_m0", billed=date(2026, 9, 28)))
    assert _refund_call(records, InMemoryRefundLedger(()), 30, charge_id="ch_m0").data["reason"] == "outside_refund_window"


def test_amount_above_remaining_is_declined():  # S4.2
    ledger = InMemoryRefundLedger((_refund("rf_h", "ch_m1", 60, date(2026, 11, 10), kind="human_approved"),))
    result = _refund_call(_records(_charge("ch_m1")), ledger, 40)
    assert result.data == {"reason": "over_remaining_amount", "remaining_usd": 27.0}


def test_pro_over_limit_returns_the_limit():  # S1.2
    result = _refund_call(_records(_charge("ch_m1")), InMemoryRefundLedger(()), 80)
    assert result.data == {"reason": "over_tier_limit", "limit_usd": 50.0, "already_refunded_usd": 0.0}


def test_split_requests_cannot_exceed_the_limit_on_one_charge():  # S8.3
    records, ledger = _records(_charge("ch_m1")), InMemoryRefundLedger(())
    assert _refund_call(records, ledger, 40, key="k1").ok
    second = _refund_call(records, ledger, 40, key="k2")
    assert second.data["reason"] == "over_tier_limit"
    assert second.data["already_refunded_usd"] == 40.0


def test_enterprise_limit_applies_cumulatively():  # S1.3
    records = _records(_charge("ch_d1", user_id="u_1002", amount=1450.0))
    ledger = InMemoryRefundLedger(())
    assert _refund_call(records, ledger, 290, user_id="u_1002", charge_id="ch_d1", key="k1").ok
    assert _refund_call(records, ledger, 435, user_id="u_1002", charge_id="ch_d1", key="k2").data["reason"] == "over_tier_limit"


def test_second_agent_refund_within_90_days_needs_review():  # S3.3
    ledger = InMemoryRefundLedger((_refund("rf_old", "ch_m0", 40, date(2026, 9, 10)),))
    records = _records(_charge("ch_m1"), _charge("ch_m0", billed=date(2026, 9, 5), period="2026-09"))
    assert _refund_call(records, ledger, 20).data["reason"] == "refund_frequency_limit"


def test_human_approved_refunds_do_not_count_toward_frequency():
    ledger = InMemoryRefundLedger((_refund("rf_h", "ch_m0", 40, date(2026, 11, 1), kind="human_approved"),))
    records = _records(_charge("ch_m1"), _charge("ch_m0", billed=date(2026, 10, 5), period="2026-10"))
    assert _refund_call(records, ledger, 20).ok


def test_retry_with_same_idempotency_key_returns_the_existing_refund():  # S10.3
    records, ledger = _records(_charge("ch_m1")), InMemoryRefundLedger(())
    first = _refund_call(records, ledger, 30, key="same")
    retry = _refund_call(records, ledger, 30, key="same")
    assert retry.ok and retry.data["refund_id"] == first.data["refund_id"]
    assert retry.data["replayed"] is True
    assert len(ledger.refunds_for("u_1001")) == 1


def test_refund_rejects_non_positive_amount():
    with pytest.raises(ToolError):
        _refund_call(_records(_charge("ch_m1")), InMemoryRefundLedger(()), 0)


def test_refund_rejects_unknown_user():
    with pytest.raises(ToolError):
        _refund_call(_records(), InMemoryRefundLedger(()), 10, user_id="u_9999")


# --- refund status ----------------------------------------------------------

def test_refund_status_lists_only_the_callers_refunds():  # S6.1
    ledger = InMemoryRefundLedger((_refund("rf_m1", "ch_m1", 30, date(2026, 11, 16)),
                                   _refund("rf_d1", "ch_d1", 290, date(2026, 11, 3), user_id="u_1002")))
    result = get_refund_status("u_1001", ledger)
    assert [r["refund_id"] for r in result.data["refunds"]] == ["rf_m1"]


def test_refund_status_for_another_users_refund_is_not_found():
    ledger = InMemoryRefundLedger((_refund("rf_d1", "ch_d1", 290, date(2026, 11, 3), user_id="u_1002"),))
    assert get_refund_status("u_1001", ledger, refund_id="rf_d1").data == {"reason": "refund_not_found"}


# --- tickets and human approval ---------------------------------------------

def _ticket(store, issue_key="u_1001:ch_m1", reason="over_tier_limit"):
    return create_ticket(store, user_id="u_1001", summary="Customer wants $80 back", reason=reason,
                         priority="normal", issue_key=issue_key, packet={"charge_id": "ch_m1"})


def test_open_ticket_for_same_issue_is_reused():  # S9.2
    store = InMemoryTicketStore()
    first, second = _ticket(store), _ticket(store)
    assert first.data["ticket_id"] == second.data["ticket_id"]
    assert second.data["existing"] is True


def test_create_ticket_requires_summary():
    with pytest.raises(ToolError):
        create_ticket(InMemoryTicketStore(), user_id=None, summary="  ", reason="x", priority="low",
                      issue_key="k", packet={})


def test_ticket_priority_rules():
    assert ticket_priority("over_tier_limit", "pro") == "normal"
    assert ticket_priority("over_tier_limit", "enterprise") == "high"
    assert ticket_priority("security_or_legal", "pro") == "high"
    assert ticket_priority("customer_requested_human", None) == "normal"


def test_human_approval_can_exceed_tier_limit_and_closes_ticket():
    store, ledger = InMemoryTicketStore(), InMemoryRefundLedger(())
    ticket_id = _ticket(store).data["ticket_id"]
    result = approve_refund(store, ledger, _records(_charge("ch_m1")), ticket_id=ticket_id, approver="agent.kim",
                            note="Approved full amount", charge_id="ch_m1", amount_usd=80, today=TODAY)
    assert result.ok and result.data["kind"] == "human_approved"
    assert store.get(ticket_id).status == "resolved"


def test_human_approval_still_cannot_exceed_the_charge():
    store, ledger = InMemoryTicketStore(), InMemoryRefundLedger(())
    ticket_id = _ticket(store).data["ticket_id"]
    result = approve_refund(store, ledger, _records(_charge("ch_m1")), ticket_id=ticket_id, approver="agent.kim",
                            note="n", charge_id="ch_m1", amount_usd=120, today=TODAY)
    assert result.data["reason"] == "over_remaining_amount"


def test_human_approval_requires_approver_and_note():
    store = InMemoryTicketStore()
    ticket_id = _ticket(store).data["ticket_id"]
    with pytest.raises(ToolError):
        approve_refund(store, InMemoryRefundLedger(()), _records(_charge("ch_m1")), ticket_id=ticket_id,
                       approver="", note="", charge_id="ch_m1", amount_usd=10, today=TODAY)


def test_approve_refund_is_not_callable_by_the_model():  # S8.4, S8.5
    assert "approve_refund" not in MODEL_TOOLS
    assert {"verify_account", "lookup_charges", "get_refund_status", "retrieve_policy",
            "issue_refund", "create_ticket"} == set(MODEL_TOOLS)


def test_records_are_immutable():
    charge = _charge("ch_m1")
    with pytest.raises(AttributeError):
        charge.amount_usd = 1.0  # type: ignore[misc]
    assert replace(charge, amount_usd=1.0).amount_usd == 1.0
