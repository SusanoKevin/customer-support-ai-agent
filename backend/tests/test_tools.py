import random

import pytest

from app.tools.accounts import load_accounts, verify_account
from app.tools.actions import create_ticket, issue_refund
from app.tools.base import ToolError, maybe_fail


def test_verify_account_returns_tier_for_matching_email_and_last4():
    result = verify_account("MAYA@example.com ", "4242")
    assert result.ok
    assert result.data["tier"] == "pro"
    assert result.data["can_take_actions"] is True


def test_verify_account_rejects_wrong_last4():
    assert verify_account("maya@example.com", "0000").ok is False


def test_verify_account_blocks_actions_when_suspended():
    result = verify_account("lee@example.com", "5150")
    assert result.ok
    assert result.data["can_take_actions"] is False


def test_verify_account_raises_on_invalid_email():
    with pytest.raises(ToolError):
        verify_account("not-an-email", "4242")


def test_mock_accounts_cover_every_tier():
    assert {a.tier for a in load_accounts()} == {"free", "pro", "enterprise"}


def test_pro_refund_within_limit_is_approved():
    result = issue_refund("u_1001", 30, "duplicate charge")
    assert result.ok
    assert result.data["refund_id"].startswith("rf_")


def test_pro_refund_over_limit_is_declined_with_limit():
    result = issue_refund("u_1001", 80, "duplicate charge")
    assert result.ok is False
    assert result.data == {"reason": "over_tier_limit", "limit_usd": 50.0}


def test_enterprise_limit_comes_from_account_not_caller():
    assert issue_refund("u_1002", 400, "invoice error").ok
    assert issue_refund("u_1001", 400, "claims to be enterprise").ok is False


def test_refund_blocked_when_contract_not_active():
    result = issue_refund("u_1003", 10, "x")
    assert result.data["reason"] == "contract_not_active"


def test_refund_rejects_unknown_user():
    with pytest.raises(ToolError):
        issue_refund("u_9999", 10, "x")


def test_refund_rejects_non_positive_amount():
    with pytest.raises(ToolError):
        issue_refund("u_1001", 0, "x")


def test_create_ticket_requires_summary():
    with pytest.raises(ToolError):
        create_ticket("u_1001", "   ", "over_tier_limit")


def test_maybe_fail_raises_retryable_error_at_full_rate():
    with pytest.raises(ToolError) as exc:
        maybe_fail("verify_account", 1.0, random.Random(0))
    assert exc.value.retryable is True


def test_maybe_fail_never_raises_at_zero_rate():
    maybe_fail("verify_account", 0.0, random.Random(0))
