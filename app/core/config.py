from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://insightquery:insightquery@localhost:5432/insightquery"
    readonly_database_url: str = (
        "postgresql+psycopg://insightquery_readonly:insightquery_readonly@localhost:5432/insightquery"
    )

    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-5"
    llm_max_output_tokens: int = 1024

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
