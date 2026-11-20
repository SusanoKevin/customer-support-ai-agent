"""Mock billing records (charges, refunds, disputes, cancellations) and read-only billing tools.

Every refund decision depends on flags computed here in code: whether a charge is in the
refund window, how much is left to refund, whether it duplicates another charge, and whether
it was billed after a cancellation took effect. The model only ever sees the results.
"""

import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from app.tools.base import ToolResult

if TYPE_CHECKING:
    from app.tools.stores import RefundLedger

BILLING_PATH = Path(__file__).resolve().parents[2] / "data" / "mock_billing.json"

REFUND_WINDOW_DAYS = 30

PaymentStatus = Literal["active", "expired", "closed"]
RefundStatus = Literal["pending", "succeeded", "failed"]
RefundKind = Literal["agent", "human_approved"]
DisputeStatus = Literal["open", "closed"]


@dataclass(frozen=True)
class PaymentMethod:
    brand: str
    last4: str
    status: PaymentStatus


@dataclass(frozen=True)
class Charge:
    charge_id: str
    user_id: str
    invoice_id: str
    invoice_period: str
    amount_usd: float
    billed_at: date
    description: str
    payment_method: PaymentMethod


@dataclass(frozen=True)
class Refund:
    refund_id: str
    charge_id: str
    user_id: str
    amount_usd: float
    reason: str
    kind: RefundKind
    status: RefundStatus
    created_at: date
    reference: str | None
    failure_reason: str | None
    idempotency_key: str | None

    @property
    def counts_against_charge(self) -> bool:
        """Failed refunds returned the money to us, so they do not reduce what is left to refund."""
        return self.status != "failed"


@dataclass(frozen=True)
class Dispute:
    charge_id: str
    status: DisputeStatus
    opened_at: date


@dataclass(frozen=True)
class Subscription:
    user_id: str
    cancelled_at: date | None
    cancellation_effective_at: date | None


@dataclass(frozen=True)
class BillingRecords:
    charges: tuple[Charge, ...]
    refunds: tuple[Refund, ...]
    disputes: tuple[Dispute, ...]
    subscriptions: tuple[Subscription, ...]


@dataclass(frozen=True)
class ChargeView:
    """A charge plus the flags the refund rules need, computed for one point in time."""

    charge: Charge
    refunded_usd: float
    refundable_remaining_usd: float
    in_window: bool
    is_duplicate: bool
    billed_after_cancellation: bool
    dispute_open: bool

    def as_dict(self) -> dict[str, Any]:
        c = self.charge
        return {
            "charge_id": c.charge_id,
            "invoice_id": c.invoice_id,
            "invoice_period": c.invoice_period,
            "amount_usd": c.amount_usd,
            "billed_at": c.billed_at.isoformat(),
            "description": c.description,
            "card": f"{c.payment_method.brand} ending {c.payment_method.last4}",
            "refunded_usd": self.refunded_usd,
            "refundable_remaining_usd": self.refundable_remaining_usd,
            "in_refund_window": self.in_window,
            "is_duplicate": self.is_duplicate,
            "billed_after_cancellation": self.billed_after_cancellation,
            "dispute_open": self.dispute_open,
        }


# --- loading ----------------------------------------------------------------

def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _charge(row: dict[str, Any]) -> Charge:
    return Charge(**{**row, "billed_at": date.fromisoformat(row["billed_at"]),
                     "payment_method": PaymentMethod(**row["payment_method"])})


def _refund(row: dict[str, Any]) -> Refund:
    return Refund(**{**row, "created_at": date.fromisoformat(row["created_at"])})


@lru_cache
def load_billing(path: Path = BILLING_PATH) -> BillingRecords:
    raw = json.loads(path.read_text())
    return BillingRecords(
        charges=tuple(_charge(r) for r in raw["charges"]),
        refunds=tuple(_refund(r) for r in raw["refunds"]),
        disputes=tuple(Dispute(r["charge_id"], r["status"], date.fromisoformat(r["opened_at"])) for r in raw["disputes"]),
        subscriptions=tuple(
            Subscription(r["user_id"], _date(r.get("cancelled_at")), _date(r.get("cancellation_effective_at")))
            for r in raw["subscriptions"]
        ),
    )


# --- computed flags ---------------------------------------------------------

def _duplicate_ids(charges: tuple[Charge, ...]) -> set[str]:
    """The later of two charges with the same amount, description and invoice period is the duplicate."""
    seen: set[tuple[str, str, float, str]] = set()
    duplicates: set[str] = set()
    for c in sorted(charges, key=lambda c: (c.billed_at, c.charge_id)):
        key = (c.user_id, c.invoice_period, c.amount_usd, c.description)
        if key in seen:
            duplicates.add(c.charge_id)
        seen.add(key)
    return duplicates


def _cancellation_effective(records: BillingRecords, user_id: str) -> date | None:
    sub = next((s for s in records.subscriptions if s.user_id == user_id), None)
    return sub.cancellation_effective_at if sub else None


def charge_views(user_id: str, records: BillingRecords, ledger: "RefundLedger", today: date) -> list[ChargeView]:
    own = tuple(c for c in records.charges if c.user_id == user_id)
    duplicates = _duplicate_ids(own)
    effective = _cancellation_effective(records, user_id)
    open_disputes = {d.charge_id for d in records.disputes if d.status == "open"}
    refunds = [r for r in ledger.refunds_for(user_id) if r.counts_against_charge]
    window_start = today - timedelta(days=REFUND_WINDOW_DAYS)

    views = []
    for c in sorted(own, key=lambda c: c.billed_at, reverse=True):
        refunded = round(sum(r.amount_usd for r in refunds if r.charge_id == c.charge_id), 2)
        views.append(ChargeView(
            charge=c,
            refunded_usd=refunded,
            refundable_remaining_usd=round(max(c.amount_usd - refunded, 0.0), 2),
            in_window=c.billed_at >= window_start,
            is_duplicate=c.charge_id in duplicates,
            billed_after_cancellation=effective is not None and c.billed_at > effective,
            dispute_open=c.charge_id in open_disputes,
        ))
    return views


def find_charge_view(user_id: str, charge_id: str, records: BillingRecords, ledger: "RefundLedger",
                     today: date) -> ChargeView | None:
    return next((v for v in charge_views(user_id, records, ledger, today) if v.charge.charge_id == charge_id), None)


# --- read-only tools --------------------------------------------------------

def lookup_charges(user_id: str, records: BillingRecords, ledger: "RefundLedger", today: date) -> ToolResult:
    views = charge_views(user_id, records, ledger, today)
    return ToolResult(ok=True, data={"charges": [v.as_dict() for v in views]})


def refund_as_dict(r: Refund) -> dict[str, Any]:
    data = asdict(r)
    data["created_at"] = r.created_at.isoformat()
    data.pop("idempotency_key")
    return data


def get_refund_status(user_id: str, ledger: "RefundLedger", refund_id: str | None = None) -> ToolResult:
    own = sorted(ledger.refunds_for(user_id), key=lambda r: r.created_at, reverse=True)
    if refund_id is None:
        return ToolResult(ok=True, data={"refunds": [refund_as_dict(r) for r in own]})
    match = next((r for r in own if r.refund_id == refund_id), None)
    if match is None:
        return ToolResult(ok=False, data={"reason": "refund_not_found"})
    return ToolResult(ok=True, data={"refunds": [refund_as_dict(match)]})
