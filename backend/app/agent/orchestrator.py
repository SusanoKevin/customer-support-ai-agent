"""Agent state machine runner: one customer message in, a stream of events out.

Nodes live in `nodes.py`. This module loads the session, runs nodes until END, emits
status and trace events around each one, enforces the step limit, and saves the session.
"""

import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import replace

from app.agent import nodes, templates
from app.agent.deps import Deps
from app.agent.llm import LLMError
from app.agent.state import STATUS_LABELS, AgentState, Node, finish_turn, start_turn
from app.events import DoneEvent, ErrorEvent, Event, StatusEvent, TraceEvent

NodeFn = Callable[[AgentState, Deps], Awaitable[nodes.Step]]

NODES: dict[Node, NodeFn] = {
    Node.CLASSIFY_INTENT: nodes.classify_intent,
    Node.VERIFY_ACCOUNT: nodes.verify_account_node,
    Node.RETRIEVE_POLICY: nodes.retrieve_policy_node,
    Node.DECIDE_ACTION: nodes.decide_action,
    Node.ISSUE_REFUND: nodes.issue_refund_node,
    Node.ESCALATE: nodes.escalate_node,
    Node.RESPOND: nodes.respond,
}
# Escalating and responding always get to run, so a long turn still ends with a handoff.
ALWAYS_RUN = frozenset({Node.ESCALATE, Node.RESPOND})
HARD_STOP_EXTRA_STEPS = 3


def _guard_steps(state: AgentState, max_steps: int) -> AgentState:
    if state.node == Node.END:
        return state
    if state.steps_taken >= max_steps + HARD_STOP_EXTRA_STEPS:
        return replace(state, node=Node.END, reply=state.reply or templates.MODEL_UNAVAILABLE)
    if state.steps_taken >= max_steps and state.node not in ALWAYS_RUN:
        return replace(state, node=Node.ESCALATE, escalation_reason="max_steps")
    return state


async def run_turn(session_id: str, message: str, deps: Deps) -> AsyncIterator[Event]:
    state = start_turn(deps.sessions.get(session_id) or AgentState(session_id=session_id), message)
    while True:
        state = _guard_steps(state, deps.settings.agent_max_steps)
        if state.node == Node.END:
            break
        node = state.node
        label = STATUS_LABELS[node]
        yield StatusEvent(step=node, state="started", label=label)
        started = time.perf_counter()
        try:
            step = await NODES[node](state, deps)
        except LLMError as exc:
            yield StatusEvent(step=node, state="failed", label=label)
            yield ErrorEvent(code=exc.code, message="The assistant is temporarily unavailable", retryable=exc.retryable)
            state = replace(state, node=Node.RESPOND, reply=templates.MODEL_UNAVAILABLE,
                            steps_taken=state.steps_taken + 1)
            continue
        for event in step.events:
            yield event
        yield StatusEvent(step=node, state="completed", label=label)
        yield TraceEvent(step=node, latency_ms=round((time.perf_counter() - started) * 1000, 1))
        state = replace(step.state, steps_taken=step.state.steps_taken + 1)

    deps.sessions.save(finish_turn(state, state.reply or ""))
    yield DoneEvent(session_id=session_id)
