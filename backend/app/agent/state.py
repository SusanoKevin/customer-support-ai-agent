"""Agent state carried across turns, and the nodes of the state machine.

State is frozen. Every node returns a new state with `dataclasses.replace`.
"""

from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Literal, Mapping

from app.agent.llm import Classification, Intent
from app.rag.retriever import Chunk
from app.tools.accounts import Account

Mode = Literal["bot", "awaiting_human"]

# Intents that need a verified account, and the subset that can move money.
ACCOUNT_INTENTS: frozenset[Intent] = frozenset({"refund_request", "billing_dispute", "refund_status"})
ACTION_INTENTS: frozenset[Intent] = frozenset({"refund_request", "billing_dispute"})

MAX_DISPUTES = 2           # customer pushes back this many times after a refusal -> human
MAX_IDENTITY_ATTEMPTS = 3  # failed verifications before escalating
HISTORY_TURNS = 6          # turns kept for prompts


class Node(StrEnum):
    CLASSIFY_INTENT = "classify_intent"
    VERIFY_ACCOUNT = "verify_account"
    RETRIEVE_POLICY = "retrieve_policy"
    DECIDE_ACTION = "decide_action"
    ISSUE_REFUND = "issue_refund"
    ESCALATE = "escalate"
    RESPOND = "respond"
    END = "end"


STATUS_LABELS: dict[Node, str] = {
    Node.CLASSIFY_INTENT: "Understanding your request...",
    Node.VERIFY_ACCOUNT: "Verifying Account Tier...",
    Node.RETRIEVE_POLICY: "Searching Knowledge Base...",
    Node.DECIDE_ACTION: "Checking policy limits...",
    Node.ISSUE_REFUND: "Processing refund...",
    Node.ESCALATE: "Connecting you to a human...",
    Node.RESPOND: "Writing response...",
}


def _empty() -> Mapping[str, Any]:
    return MappingProxyType({})


@dataclass(frozen=True)
class AgentState:
    session_id: str
    turn: int = 0
    history: tuple[tuple[str, str], ...] = ()  # (role, text)

    # Carried across turns
    account: Account | None = None
    identity_failures: int = 0
    pending: Classification | None = None      # request waiting for identity
    dispute_count: int = 0
    last_was_refusal: bool = False
    mode: Mode = "bot"
    open_ticket_id: str | None = None

    # Reset every turn
    user_message: str = ""
    classification: Classification | None = None
    chunks: tuple[Chunk, ...] = ()
    facts: Mapping[str, Any] = field(default_factory=_empty)
    tool_log: tuple[str, ...] = ()
    target_charge_id: str | None = None
    escalation_reason: str | None = None
    reply: str | None = None
    steps_taken: int = 0
    node: Node = Node.CLASSIFY_INTENT

    @property
    def intent(self) -> Intent | None:
        return self.classification.intent if self.classification else None

    def with_fact(self, key: str, value: Any) -> "AgentState":
        return replace(self, facts=MappingProxyType({**self.facts, key: value}))

    def logged(self, entry: str) -> "AgentState":
        return replace(self, tool_log=(*self.tool_log, entry))


def start_turn(state: AgentState, message: str) -> AgentState:
    return replace(
        state, turn=state.turn + 1, user_message=message, classification=None, chunks=(), facts=_empty(),
        tool_log=(), target_charge_id=None, escalation_reason=None, reply=None, steps_taken=0,
        node=Node.CLASSIFY_INTENT,
    )


def finish_turn(state: AgentState, reply: str) -> AgentState:
    history = (*state.history, ("customer", state.user_message), ("assistant", reply))
    return replace(state, history=history[-2 * HISTORY_TURNS:], node=Node.END)


def recent_turns(state: AgentState) -> str:
    return "\n".join(f"{role}: {text}" for role, text in state.history)
