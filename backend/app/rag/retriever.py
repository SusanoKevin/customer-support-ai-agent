"""Vector retrieval over pgvector."""

from dataclasses import asdict, dataclass
from typing import Any, Protocol

import numpy as np
from psycopg_pool import AsyncConnectionPool

from app.rag.embeddings import Embedder

SEARCH_SQL = """
    select chunk_id, doc, heading, text, tiers,
           1 - (embedding <=> %(q)s) as similarity
    from chunks
    where %(tier)s = any(tiers)
    order by embedding <=> %(q)s
    limit %(k)s
"""


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc: str
    heading: str
    text: str
    tiers: tuple[str, ...]
    similarity: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class Retriever(Protocol):
    async def search(self, query: str, tier: str, top_k: int) -> list[Chunk]: ...


class PgVectorRetriever:
    def __init__(self, pool: AsyncConnectionPool, embedder: Embedder) -> None:
        self._pool = pool
        self._embedder = embedder

    async def search(self, query: str, tier: str, top_k: int) -> list[Chunk]:
        if not query.strip():
            return []
        [vector] = await self._embedder.embed([query], task="RETRIEVAL_QUERY")
        async with self._pool.connection() as conn:
            cur = await conn.execute(SEARCH_SQL, {"q": np.array(vector), "tier": tier, "k": top_k})
            rows = await cur.fetchall()
        return [
            Chunk(chunk_id, doc, heading, text, tuple(tiers), float(similarity))
            for chunk_id, doc, heading, text, tiers, similarity in rows
        ]
