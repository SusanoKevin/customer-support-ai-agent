"""Everything a turn needs, built once at startup and injected, so tests swap in fakes."""

import random
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date

from app.agent.llm import LLM
from app.agent.sessions import SessionStore
from app.agent.state import EMAIL_FAILURE_LIMIT, EMAIL_FAILURE_WINDOW_S
from app.config import Settings
from app.rag.retriever import Retriever
from app.ratelimit import SlidingWindowLimiter
from app.tools.billing import BillingRecords
from app.tools.stores import DemoWorkspaces, RefundLedger, TicketStore
from app.voice import VoiceTokenIssuer


@dataclass(frozen=True)
class Deps:
    llm: LLM
    retriever: Retriever
    records: BillingRecords
    ledger: RefundLedger
    tickets: TicketStore
    sessions: SessionStore
    settings: Settings
    today: Callable[[], date] = date.today
    rng: random.Random = field(default_factory=random.Random)
    retry_delay_s: float = 0.3
    voice: VoiceTokenIssuer | None = None  # None = voice disabled (no key or no Live model)
    # Failed identity checks per email, shared by every session, so "New session" does not reset guessing.
    email_failures: SlidingWindowLimiter = field(
        default_factory=lambda: SlidingWindowLimiter(EMAIL_FAILURE_LIMIT, EMAIL_FAILURE_WINDOW_S))
    # Set on the public demo: each visitor gets their own refunds and tickets (review H1). None = shared stores.
    workspaces: DemoWorkspaces | None = None

    def for_workspace(self, workspace_id: str) -> "Deps":
        """The stores this visitor sees. The email lockout stays shared on purpose (log P16)."""
        if self.workspaces is None:
            return self
        ledger, tickets = self.workspaces.stores_for(workspace_id)
        return replace(self, ledger=ledger, tickets=tickets)
