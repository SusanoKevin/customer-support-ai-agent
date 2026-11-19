"""Chunk policy docs, embed them, and upsert into pgvector. Safe to re-run."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from psycopg_pool import AsyncConnectionPool

from app.rag.chunking import RawChunk, chunk_markdown
from app.rag.embeddings import Embedder

POLICIES_DIR = Path(__file__).resolve().parents[2] / "data" / "policies"

UPSERT_SQL = """
    insert into chunks (chunk_id, doc, heading, text, tiers, embedding)
    values (%s, %s, %s, %s, %s, %s)
    on conflict (chunk_id) do update set
        doc = excluded.doc, heading = excluded.heading, text = excluded.text,
        tiers = excluded.tiers, embedding = excluded.embedding
"""
DELETE_STALE_SQL = "delete from chunks where not (chunk_id = any(%s))"


@dataclass(frozen=True)
class IngestRow:
    chunk: RawChunk
    embedding: tuple[float, ...]


def load_chunks(policies_dir: Path = POLICIES_DIR) -> list[RawChunk]:
    chunks = [
        chunk
        for path in sorted(policies_dir.glob("*.md"))
        for chunk in chunk_markdown(path.stem, path.read_text())
    ]
    if not chunks:
        raise RuntimeError(f"No policy chunks found in {policies_dir}")
    return chunks


def embedding_text(chunk: RawChunk) -> str:
    """Heading is prepended so short sections still carry their topic."""
    return f"{chunk.heading}\n{chunk.text}"


async def build_rows(chunks: list[RawChunk], embedder: Embedder) -> list[IngestRow]:
    vectors = await embedder.embed([embedding_text(c) for c in chunks], task="RETRIEVAL_DOCUMENT")
    if len(vectors) != len(chunks):
        raise RuntimeError(f"Expected {len(chunks)} embeddings, got {len(vectors)}")
    return [IngestRow(chunk=c, embedding=tuple(v)) for c, v in zip(chunks, vectors)]


async def write_rows(pool: AsyncConnectionPool, rows: list[IngestRow]) -> int:
    """Upsert all rows, delete chunks no longer in the docs. Returns how many were deleted."""
    params = [
        (r.chunk.chunk_id, r.chunk.doc, r.chunk.heading, r.chunk.text, list(r.chunk.tiers), np.array(r.embedding))
        for r in rows
    ]
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.executemany(UPSERT_SQL, params)
        stale = await conn.execute(DELETE_STALE_SQL, ([r.chunk.chunk_id for r in rows],))
        return stale.rowcount
