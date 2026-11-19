"""CLI: python -m scripts.ingest  (run from backend/)"""

import asyncio
import logging
import sys

import psycopg

from app.config import get_settings
from app.db import apply_schema, make_pool
from app.rag.embeddings import GeminiEmbedder
from app.rag.ingest import build_rows, load_chunks, write_rows

logger = logging.getLogger("ingest")


async def main() -> int:
    settings = get_settings()

    # Database first: fail fast before spending embedding quota.
    try:
        await apply_schema(settings.database_url)
    except psycopg.OperationalError as exc:
        logger.error("Database connection failed: %s", str(exc).splitlines()[-1])
        return 1

    embedder = GeminiEmbedder(settings.gemini_api_key, settings.gemini_embed_model, settings.embed_dim)
    chunks = load_chunks()
    logger.info("Embedding %d chunks with %s", len(chunks), settings.gemini_embed_model)
    rows = await build_rows(chunks, embedder)

    async with make_pool(settings.database_url) as pool:
        removed = await write_rows(pool, rows)
    logger.info("Upserted %d chunks, removed %d stale", len(rows), removed)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(asyncio.run(main()))
