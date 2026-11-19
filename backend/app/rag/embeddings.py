"""Embedding providers behind a small protocol so tests can use a fake."""

from typing import Literal, Protocol

from google import genai
from google.genai import types

TaskType = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]
BATCH_SIZE = 50


class Embedder(Protocol):
    dim: int

    async def embed(self, texts: list[str], task: TaskType) -> list[list[float]]: ...


class GeminiEmbedder:
    def __init__(self, api_key: str, model: str, dim: int) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set in backend/.env")
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self.dim = dim

    async def embed(self, texts: list[str], task: TaskType) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            batch = texts[start : start + BATCH_SIZE]
            response = await self._client.aio.models.embed_content(
                model=self._model,
                contents=batch,
                config=types.EmbedContentConfig(task_type=task, output_dimensionality=self.dim),
            )
            vectors.extend(list(e.values) for e in response.embeddings)
        if any(len(v) != self.dim for v in vectors):
            raise RuntimeError(f"Embedding model returned vectors that are not {self.dim}-dim")
        return vectors
