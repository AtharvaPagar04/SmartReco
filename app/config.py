from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SmartReco"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "development-only-change-me"
    database_url: str = "sqlite+aiosqlite:///./smartreco.db"
    mesh_api_key: str = ""
    mesh_embedding_model: str = "openai/text-embedding-3-small"
    embedding_schema_version: int = 1
    qdrant_mode: str = "local"
    qdrant_path: str = "./data/qdrant"
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = "smartreco_courses"
    vector_size: int = 1536
    vector_sync_interval_seconds: int = 30
    vector_sync_batch_size: int = 20
    vector_sync_max_attempts: int = 5
    vector_processing_timeout_seconds: int = 300
    event_batch_max_size: int = 50
    event_metadata_max_bytes: int = 4096
    event_queue_max_size: int = 100
    session_cookie_name: str = "smartreco_session"
    session_https_only: bool = False
    session_max_age_seconds: int = 604800
    admin_email: str = "admin@smartreco.org"
    admin_password: str = "ChangeMe123!"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @field_validator("qdrant_mode")
    @classmethod
    def validate_qdrant_mode(cls, value: str) -> str:
        if value not in {"local", "remote"}:
            raise ValueError("QDRANT_MODE must be local or remote")
        return value

    def validate_runtime(self) -> None:
        if self.app_env == "production" and self.secret_key == "development-only-change-me":
            raise ValueError("SECRET_KEY must be changed in production")
        if self.qdrant_mode == "remote" and not self.qdrant_url:
            raise ValueError("QDRANT_URL is required when QDRANT_MODE=remote")
        if self.vector_size < 1 or self.event_batch_max_size > 50:
            raise ValueError("Invalid vector or event limits")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
