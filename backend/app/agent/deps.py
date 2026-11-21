"""Everything a turn needs, built once at startup and injected, so tests swap in fakes."""

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from app.agent.llm import LLM
from app.agent.sessions import SessionStore
from app.config import Settings
from app.rag.retriever import Retriever
from app.tools.billing import BillingRecords
from app.tools.stores import RefundLedger, TicketStore
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
