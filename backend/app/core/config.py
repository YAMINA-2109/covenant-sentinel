from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from process env then backend/.env."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    vultr_api_key: str = ""
    vultr_base_url: str = "https://api.vultrinference.com/v1"
    vultr_chat_model: str = "Qwen/Qwen3.5-397B-A17B"
    # VultronRetriever reranker for the hybrid retrieval stage ("" -> pure BM25)
    vultr_retriever_model: str = "vultr/VultronRetrieverPrime-Qwen3.5-8B"

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    trace_dir: str = "traces"


@lru_cache
def get_settings() -> Settings:
    return Settings()
