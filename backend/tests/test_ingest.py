import pytest

from app.rag.ingest import build_rows, embedding_text, load_chunks


class FakeEmbedder:
    dim = 4

    def __init__(self, count_override: int | None = None) -> None:
        self.calls: list[tuple[int, str]] = []
        self._count_override = count_override

    async def embed(self, texts: list[str], task: str) -> list[list[float]]:
        self.calls.append((len(texts), task))
        n = self._count_override if self._count_override is not None else len(texts)
        return [[float(i), 0.0, 0.0, 1.0] for i in range(n)]


def test_load_chunks_reads_every_policy_with_unique_ids():
    chunks = load_chunks()
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))
    assert {c.doc for c in chunks} == {"refunds", "plans", "troubleshooting", "escalation"}


def test_embedding_text_prepends_heading():
    chunk = load_chunks()[0]
    assert embedding_text(chunk).startswith(chunk.heading + "\n")


async def test_build_rows_embeds_all_chunks_in_one_document_call():
    chunks = load_chunks()
    embedder = FakeEmbedder()
    rows = await build_rows(chunks, embedder)
    assert embedder.calls == [(len(chunks), "RETRIEVAL_DOCUMENT")]
    assert [r.chunk for r in rows] == chunks
    assert all(len(r.embedding) == 4 for r in rows)


async def test_build_rows_fails_when_embedding_count_mismatches():
    with pytest.raises(RuntimeError):
        await build_rows(load_chunks(), FakeEmbedder(count_override=1))
