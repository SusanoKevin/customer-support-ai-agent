"""Confidence gates. Deterministic so they are easy to test and explain."""

import re
from dataclasses import dataclass

from app.rag.retriever import Chunk

CITATION = re.compile(r"\[(\S+?:\d+:\d+)\]")  # e.g. [refunds:1:0]
CHUNK_ID = re.compile(r"[a-z0-9_-]+:\d+:\d+")
BRACKET_GROUP = re.compile(r"\[([^\[\]]*)\]")


def normalize_citations(answer: str) -> str:
    """Rewrite a bracket that mixes ids with other text, like [refunds:8:0, account facts], as [refunds:8:0].

    Without this the gate never sees the id inside, and the customer sees a malformed chip (log L37)."""
    def clean(match: re.Match[str]) -> str:
        ids = CHUNK_ID.findall(match.group(1))
        return "".join(f"[{i}]" for i in ids) if ids else match.group(0)
    return BRACKET_GROUP.sub(clean, answer)


@dataclass(frozen=True)
class GateResult:
    passed: bool
    reason: str


PASSED = GateResult(passed=True, reason="ok")


def retrieval_gate(chunks: list[Chunk], min_similarity: float, min_chunks: int) -> GateResult:
    confident = [c for c in chunks if c.similarity >= min_similarity]
    if len(confident) < min_chunks:
        return GateResult(passed=False, reason="low_retrieval_confidence")
    return PASSED


def grounding_gate(answer: str, chunks: list[Chunk]) -> GateResult:
    """Answer must cite at least one retrieved chunk, and only retrieved chunks."""
    cited = set(CITATION.findall(answer))
    if not cited:
        return GateResult(passed=False, reason="uncited_answer")
    if not cited <= {c.chunk_id for c in chunks}:
        return GateResult(passed=False, reason="unknown_citation")
    return PASSED
