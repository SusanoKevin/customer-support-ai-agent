"""Stores for records the agent creates: refunds and support tickets.

Records are frozen; a store only ever adds a record or replaces one with a new version.
In-memory versions run the demo and the tests. Postgres versions replace them later (L8, L12)
behind the same protocols.
"""

from dataclasses import dataclass, field
from datetime import date
from types import MappingProxyType
from typing import Any, Literal, Mapping, Protocol

from app.tools.billing import Refund

Priority = Literal["low", "normal", "high"]
TicketStatus = Literal["open", "resolved"]


@dataclass(frozen=True)
class Ticket:
    ticket_id: str
    user_id: str | None
    summary: str
    reason: str
    priority: Priority
    issue_key: str
    status: TicketStatus
    created_at: date
    packet: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def as_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "user_id": self.user_id,
            "summary": self.summary,
            "reason": self.reason,
            "priority": self.priority,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "packet": dict(self.packet),
        }


class RefundLedger(Protocol):
    def refunds_for(self, user_id: str) -> tuple[Refund, ...]: ...

    def find_by_key(self, idempotency_key: str) -> Refund | None: ...

    def add(self, refund: Refund) -> None: ...


class TicketStore(Protocol):
    def get(self, ticket_id: str) -> Ticket | None: ...

    def find_open(self, issue_key: str) -> Ticket | None: ...

    def save(self, ticket: Ticket) -> None: ...


class InMemoryRefundLedger:
    def __init__(self, seed: tuple[Refund, ...]) -> None:
        self._refunds: tuple[Refund, ...] = tuple(seed)

    def refunds_for(self, user_id: str) -> tuple[Refund, ...]:
        return tuple(r for r in self._refunds if r.user_id == user_id)

    def find_by_key(self, idempotency_key: str) -> Refund | None:
        return next((r for r in self._refunds if r.idempotency_key == idempotency_key), None)

    def add(self, refund: Refund) -> None:
        self._refunds = (*self._refunds, refund)


class DemoWorkspaces:
    """One refund ledger and ticket store per visitor, seeded from the demo billing data.

    The public demo shares one server, so with a single ledger the first visitor's refund blocks the next
    visitor's identical demo (review H1). Keyed by a browser-held workspace id, so "New session" in one
    browser keeps that visitor's refunds and the 90-day rule still holds for them.
    """

    def __init__(self, seed: tuple[Refund, ...]) -> None:
        self._seed = tuple(seed)
        self._stores: dict[str, tuple[InMemoryRefundLedger, "InMemoryTicketStore"]] = {}

    def stores_for(self, workspace_id: str) -> tuple["InMemoryRefundLedger", "InMemoryTicketStore"]:
        if workspace_id not in self._stores:
            fresh = (InMemoryRefundLedger(self._seed), InMemoryTicketStore())
            self._stores = {**self._stores, workspace_id: fresh}
        return self._stores[workspace_id]


class InMemoryTicketStore:
    def __init__(self) -> None:
        self._tickets: dict[str, Ticket] = {}

    def get(self, ticket_id: str) -> Ticket | None:
        return self._tickets.get(ticket_id)

    def find_open(self, issue_key: str) -> Ticket | None:
        return next((t for t in self._tickets.values() if t.issue_key == issue_key and t.status == "open"), None)

    def save(self, ticket: Ticket) -> None:
        self._tickets = {**self._tickets, ticket.ticket_id: ticket}
