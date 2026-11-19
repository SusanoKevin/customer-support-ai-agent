"""Postgres (Supabase) connection pool and schema."""

from pathlib import Path

from pgvector.psycopg import register_vector_async
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "db" / "schema.sql"

# prepare_threshold=None keeps psycopg safe behind Supabase's transaction pooler.
CONNECT_KWARGS = {"prepare_threshold": None}


async def apply_schema(database_url: str) -> None:
    """Uses one plain connection, so bad credentials fail once instead of the pool
    retrying and tripping Supabase's auth circuit breaker. Must run before the pool
    opens, because pooled connections register the `vector` type on connect."""
    async with await AsyncConnection.connect(
        database_url, connect_timeout=10, autocommit=True, **CONNECT_KWARGS
    ) as conn:
        await conn.execute(SCHEMA_PATH.read_text())


def make_pool(database_url: str) -> AsyncConnectionPool:
    if not database_url:
        raise ValueError("DATABASE_URL is not set in backend/.env")
    return AsyncConnectionPool(
        database_url,
        min_size=1,
        max_size=5,
        open=False,
        configure=register_vector_async,
        kwargs=CONNECT_KWARGS,
    )
