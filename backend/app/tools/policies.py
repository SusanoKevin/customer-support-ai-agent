"""Tool 2: retrieve tier-filtered policy chunks. Thin wrapper over the RAG retriever."""

import logging

from app.rag.retriever import Retriever
from app.tools.base import ToolError, ToolResult

logger = logging.getLogger("support_agent")


async def retrieve_policy(retriever: Retriever, query: str, tier: str | None, top_k: int = 4) -> ToolResult:
    try:
        chunks = await retriever.search(query=query, tier=tier, top_k=top_k)
    except Exception as exc:  # embedder and database raise many types; all mean "search unavailable" (log B2)
        logger.warning("Policy search failed: %r", exc)
        raise ToolError(f"Policy search unavailable ({type(exc).__name__})", retryable=True) from exc
    return ToolResult(
        ok=bool(chunks),
        data={"chunks": [c.as_dict() for c in chunks]},
    )
