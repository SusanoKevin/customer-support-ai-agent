"""Session storage for `AgentState` between turns. In memory for now; Postgres behind the same protocol later (L12)."""

from typing import Protocol

from app.agent.state import AgentState


class SessionStore(Protocol):
    def get(self, session_id: str) -> AgentState | None: ...

    def save(self, state: AgentState) -> None: ...


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, AgentState] = {}

    def get(self, session_id: str) -> AgentState | None:
        return self._sessions.get(session_id)

    def save(self, state: AgentState) -> None:
        self._sessions = {**self._sessions, state.session_id: state}
