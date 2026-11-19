"""Tool 2: retrieve tier-filtered policy chunks. Thin wrapper over the RAG retriever."""

from app.rag.retriever import Retriever
from app.tools.base import ToolResult


async def retrieve_policy(retriever: Retriever, query: str, tier: str, top_k: int = 4) -> ToolResult:
    chunks = await retriever.search(query=query, tier=tier, top_k=top_k)
    return ToolResult(
        ok=bool(chunks),
        data={"chunks": [c.as_dict() for c in chunks]},
    )
