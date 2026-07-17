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
    # Any OpenAI-compatible provider. For xAI/Grok set:
    #   LLM_API_KEY=xai-...   LLM_BASE_URL=https://api.x.ai/v1   LLM_MODEL=grok-3-mini
    llm_api_key: str = ""
    llm_base_url: str | None = None
    llm_model: str = "gpt-4o-mini"

    # ---- Embeddings ----
    # "local"  -> fastembed, ONNX on CPU, no key, no network at query time
    # "openai" -> OpenAI embeddings API
    # xAI has no public embeddings endpoint, so a Grok LLM still needs one of
    # these for retrieval. They are independent choices on purpose.
    embedding_provider: str = "local"
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # ---- RAG ----
    chunk_size: int = 800
    chunk_overlap: int = 120
    retrieval_top_k: int = 5

    # ---- Storage ----
    upload_dir: str = "./data/uploads"
    chroma_dir: str = "./data/chroma"

    # Back-compat: earlier phases used OPENAI_API_KEY.
    openai_api_key: str = ""

    @computed_field
    @property
    def resolved_llm_key(self) -> str:
        return self.llm_api_key or self.openai_api_key

    @computed_field
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
