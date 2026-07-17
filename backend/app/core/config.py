"""Centralised configuration management.

All settings come from environment variables / .env — nothing is hardcoded.
"""

from functools import lru_cache

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- App ----
    app_name: str = "SupportOps AI"
    environment: str = "development"
    debug: bool = True
    log_level: str = "INFO"

    # ---- API ----
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000"

    # ---- Auth ----
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # ---- Database (SQLAlchemy) ----
    database_url: str = "sqlite:///./data/supportops.db"

    # ---- ChromaDB (persistent local client) ----
    chroma_collection: str = "enterprise_knowledge"

    # ---- LLM ----
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    # ---- RAG ----
    chunk_size: int = 800
    chunk_overlap: int = 120
    retrieval_top_k: int = 5

    # ---- Storage ----
    upload_dir: str = "./data/uploads"
    chroma_dir: str = "./data/chroma"

    @computed_field
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
