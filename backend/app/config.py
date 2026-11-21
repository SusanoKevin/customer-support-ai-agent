"""Typed settings loaded from environment. Fails fast on invalid values."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    gemini_api_key: str = ""
    # Small model labels the message, stronger model writes the answer (log P3).
    gemini_classify_model: str = "gemini-3.5-flash-lite"
    gemini_answer_model: str = "gemini-3.8-flash"
    llm_timeout_s: float = Field(default=20.0, gt=0, le=120)
    gemini_live_model: str = ""
    gemini_embed_model: str = "gemini-embedding-001"
    embed_dim: int = Field(default=768, ge=64, le=3072)  # must match vector(768) in db/schema.sql
    groq_api_key: str = ""
    groq_chat_model: str = ""

    database_url: str = ""
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""

    # Calibrated 2026-11-18 on gemini-embedding-001 @768: in-scope 0.66-0.77, out-of-scope 0.51-0.59.
    rag_min_similarity: float = Field(default=0.62, ge=0.0, le=1.0)
    rag_min_chunks: int = Field(default=1, ge=1)
    agent_max_steps: int = Field(default=6, ge=1, le=20)
    simulate_tool_failure_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    rate_limit_per_minute: int = Field(default=20, ge=1)
    frontend_origin: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
