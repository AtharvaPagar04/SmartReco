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
    mesh_base_url: str = "https://api.meshapi.ai/v1"
    mesh_embedding_model: str = "openai/text-embedding-3-small"
    mesh_chat_model: str = ""
    mesh_request_timeout_seconds: int = 30
    mesh_max_retries: int = 1
    mesh_total_budget_seconds: int = 70
    embedding_schema_version: int = 1
    related_courses_enabled: bool = True
    related_courses_limit: int = 2
    related_courses_candidate_limit: int = 10
    related_courses_cache_ttl_seconds: int = 1800
    related_courses_semantic_weight: float = 0.60
    related_courses_category_weight: float = 0.20
    related_courses_tag_weight: float = 0.15
    related_courses_difficulty_weight: float = 0.05
    related_courses_timeout_seconds: int = 3
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
    recommendations_enabled: bool = True
    recommendation_event_window_days: int = 30
    recommendation_signal_half_life_days: int = 14
    recommendation_min_meaningful_events: int = 3
    recommendation_min_signal_score: float = 6.0
    recommendation_cooldown_minutes: int = 30
    recommendation_ttl_hours: int = 6
    recommendation_max_candidates: int = 30
    recommendation_final_count: int = 3
    recommendation_display_limit: int = 3
    recommendation_max_refinements: int = 1
    recommendation_job_batch_size: int = 10
    recommendation_lease_minutes: int = 10
    learning_path_builder_enabled: bool = True
    learning_path_chat_model: str = ""
    learning_path_prompt_version: str = "1"
    learning_path_max_candidates: int = 16
    learning_path_max_courses: int = 4
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "smartreco"
    email_provider: str = "console"
    email_from_address: str = ""
    email_from_name: str = "SmartReco"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    app_base_url: str = "http://127.0.0.1:8001"
    app_timezone: str = "UTC"
    payments_enabled: bool = True
    payments_mode: str = "demo"
    cart_max_items: int = 25
    default_currency: str = "USD"

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
        if self.vector_size < 1 or self.event_batch_max_size > 50 or self.mesh_total_budget_seconds < 1:
            raise ValueError("Invalid vector or event limits")
        if self.payments_mode != "demo":
            raise ValueError("Only demo payments are enabled in this phase")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
