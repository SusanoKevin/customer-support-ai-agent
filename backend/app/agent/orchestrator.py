"""Agent state machine. See PLAN.md for the state diagram.

Day 2: implement one function per Node. Each takes AgentState and returns a new
state (dataclasses.replace) plus the events to emit.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.events import Event
from app.rag.retriever import Chunk
from app.tools.accounts import Account


class Node(StrEnum):
    CLASSIFY_INTENT = "classify_intent"
    VERIFY_ACCOUNT = "verify_account"
    RETRIEVE_POLICY = "retrieve_policy"
    DECIDE_ACTION = "decide_action"
    ISSUE_REFUND = "issue_refund"
    CREATE_TICKET = "create_ticket"
    RESPOND = "respond"
    ESCALATE = "escalate"
    END = "end"


STATUS_LABELS: dict[Node, str] = {
    Node.CLASSIFY_INTENT: "Understanding your request...",
    Node.VERIFY_ACCOUNT: "Verifying Account Tier...",
    Node.RETRIEVE_POLICY: "Searching Knowledge Base...",
    Node.DECIDE_ACTION: "Checking policy limits...",
    Node.ISSUE_REFUND: "Processing refund...",
    Node.CREATE_TICKET: "Creating support ticket...",
    Node.RESPOND: "Writing response...",
    Node.ESCALATE: "Connecting you to a human...",
}


@dataclass(frozen=True)
class AgentState:
    session_id: str
    user_message: str
    history: tuple[dict[str, str], ...] = ()
    account: Account | None = None
    chunks: tuple[Chunk, ...] = ()
    tool_results: tuple[dict[str, Any], ...] = ()
    escalation_reason: str | None = None
    steps_taken: int = 0
    node: Node = Node.CLASSIFY_INTENT


async def run_turn(state: AgentState) -> AsyncIterator[Event]:
    """Drive the state machine until END or AGENT_MAX_STEPS. TODO Day 2."""
    raise NotImplementedError
    yield  # makes this an async generator so the signature is already final
