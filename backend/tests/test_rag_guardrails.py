from pathlib import Path

from app.agent.guardrails import grounding_gate, normalize_citations, retrieval_gate
from app.rag.chunking import chunk_markdown
from app.rag.retriever import Chunk

POLICIES = Path(__file__).resolve().parents[1] / "data" / "policies"


def _chunk(cid: str, sim: float) -> Chunk:
    return Chunk(chunk_id=cid, doc="refunds", heading="h", text="t", tiers=("pro",), similarity=sim)


def test_chunking_splits_on_headings_and_reads_tier_tags():
    chunks = chunk_markdown("refunds", (POLICIES / "refunds.md").read_text())
    assert len(chunks) == 10
    pro = next(c for c in chunks if c.heading == "Pro tier refund limits")
    assert pro.tiers == ("pro",)
    assert "Tiers:" not in pro.text


def test_every_policy_file_produces_chunks():
    for path in POLICIES.glob("*.md"):
        assert chunk_markdown(path.stem, path.read_text()), path.name


def test_retrieval_gate_fails_below_threshold():
    result = retrieval_gate([_chunk("refunds:0:0", 0.6)], min_similarity=0.75, min_chunks=1)
    assert result.passed is False
    assert result.reason == "low_retrieval_confidence"


def test_retrieval_gate_passes_with_confident_chunk():
    assert retrieval_gate([_chunk("refunds:0:0", 0.82)], 0.75, 1).passed


def test_retrieval_gate_fails_on_empty_results():
    assert retrieval_gate([], 0.75, 1).passed is False


def test_grounding_gate_requires_citation():
    assert grounding_gate("You can get a refund.", [_chunk("refunds:1:0", 0.9)]).reason == "uncited_answer"


def test_grounding_gate_rejects_unknown_citation():
    result = grounding_gate("Yes [plans:9:0]", [_chunk("refunds:1:0", 0.9)])
    assert result.reason == "unknown_citation"


def test_grounding_gate_passes_with_known_citation():
    assert grounding_gate("Up to $50 [refunds:1:0]", [_chunk("refunds:1:0", 0.9)]).passed


def test_normalize_citations_keeps_only_ids_in_a_mixed_bracket():  # L37
    assert normalize_citations("Up to $50 [refunds:8:0, account facts].") == "Up to $50 [refunds:8:0]."
    assert normalize_citations("[refunds:1:0; plans:2:0]") == "[refunds:1:0][plans:2:0]"


def test_normalize_citations_leaves_clean_citations_and_plain_brackets_alone():
    assert normalize_citations("Yes [refunds:1:0] [note]") == "Yes [refunds:1:0] [note]"
