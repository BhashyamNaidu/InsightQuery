from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://insightquery:insightquery@localhost:5433/insightquery"
    readonly_database_url: str = (
        "postgresql+psycopg://insightquery_readonly:insightquery_readonly@localhost:5433/insightquery"
    )

    # --- LLM provider (see docs/LLM_STRATEGY.md) ---
    # "ollama" is the default deliberately: it's the only provider that works out of
    # the box with no API key and no cost. "anthropic" is supported for anyone who
    # already has a key and wants stronger output quality; "none" disables LLM
    # features entirely (SQL/RAG/deterministic analytics still work — see
    # app/services/investigation.py's graceful-degradation paths).
    llm_provider: str = "ollama"
    llm_max_output_tokens: int = 1024

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    ollama_timeout_seconds: float = 120.0

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384

    app_env: str = "development"
    log_level: str = "INFO"
    sql_row_limit: int = 200
    sql_statement_timeout_ms: int = 5000
    api_port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
