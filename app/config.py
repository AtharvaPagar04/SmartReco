from functools import lru_cache
from typing import Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from app.config_loader import SUPPORTED_ENVS, TomlConfigSettingsSource, load_toml_settings

KNOWN_PLACEHOLDER_SECRETS = {
    "replace-with-a-long-random-secret",
    "development-only-change-me",
    "changeme",
    "secret",
    "development-secret",
}


class Settings(BaseSettings):
    app_name: str = "SmartReco"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "development-only-change-me"
    database_url: str = "sqlite+aiosqlite:///./smartreco.db"
    run_migrations_on_start: bool = False
    mesh_api_key: str = ""
    mesh_base_url: str = "https://api.meshapi.ai/v1"
    mesh_embedding_model: str = "openai/text-embedding-3-small"
    mesh_chat_model: str = "deepseek/deepseek-v4-flash"
    mesh_request_timeout_seconds: int = 30
    mesh_max_retries: int = 1
    mesh_total_budget_seconds: int = 70
    embedding_schema_version: int = 1
    related_courses_enabled: bool = True
    related_courses_limit: int = 2
    related_courses_candidate_limit: int = 10
    related_courses_cache_ttl_seconds: int = 1800
    related_courses_semantic_weight: float = 0.45
    related_courses_category_weight: float = 0.15
    related_courses_tag_weight: float = 0.10
    related_courses_activity_weight: float = 0.25
    related_courses_difficulty_weight: float = 0.05
    related_courses_min_semantic_score: float = 0.45
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
    learning_path_max_courses: int = 8
    learning_path_max_repairs: int = 1
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "smartreco"
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    email_provider: str = "console"
    email_from_address: str = Field("", validation_alias=AliasChoices("EMAIL_FROM_ADDRESS", "EMAIL_FROM"))
    email_from_name: str = "SmartReco"
    resend_api_key: str = Field("", validation_alias=AliasChoices("RESEND_API_KEY"))
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True

    @property
    def email_from(self) -> str:
        return self.email_from_address
    app_base_url: str = "http://127.0.0.1:8001"
    session_followup_enabled: bool = True
    session_followup_inactivity_minutes: int = 1
    session_followup_scan_interval_seconds: int = 15
    session_followup_min_signal_score: float = 3.0
    session_followup_max_courses: int = 3
    session_followup_cooldown_hours: int = 6
    session_followup_min_meaningful_events: int = 1
    google_auth_enabled: bool = False
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://127.0.0.1:8001/auth/google/callback"
    google_oidc_discovery_url: str = "https://accounts.google.com/.well-known/openid-configuration"
    google_oauth_state_ttl_seconds: int = 600
    google_request_timeout_seconds: int = 10
    app_timezone: str = "UTC"
    payments_enabled: bool = True
    payments_mode: str = "demo"
    cart_max_items: int = 25
    default_currency: str = "USD"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TomlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value


    @field_validator("qdrant_mode")
    @classmethod
    def validate_qdrant_mode(cls, value: str) -> str:
        if value not in {"local", "remote"}:
            raise ValueError("QDRANT_MODE must be local or remote")
        return value

    def validate_runtime(self) -> None:
        validate_runtime_configuration(self)


def validate_runtime_configuration(settings: Settings) -> None:
    env = settings.app_env.lower()
    if env not in SUPPORTED_ENVS:
        raise ValueError(f"Unsupported APP_ENV: '{settings.app_env}'. Must be one of {sorted(SUPPORTED_ENVS)}.")

    if env == "production":
        if settings.debug:
            raise ValueError("Production configuration error: DEBUG mode must be disabled in production.")
        if not settings.session_https_only:
            raise ValueError("Production configuration error: SESSION_HTTPS_ONLY must be enabled in production.")
        if settings.secret_key in KNOWN_PLACEHOLDER_SECRETS:
            raise ValueError("Production configuration error: SECRET_KEY must be changed in production.")
        if settings.email_provider == "console":
            raise ValueError("Production configuration error: EMAIL_PROVIDER must be configured for a production backend (e.g. smtp).")
    elif env != "test":
        if settings.secret_key in KNOWN_PLACEHOLDER_SECRETS and settings.secret_key != "development-only-change-me":
            raise ValueError("SECRET_KEY must not use a known placeholder value.")

    if settings.qdrant_mode == "remote":
        if not settings.qdrant_url:
            raise ValueError("Qdrant configuration error: QDRANT_URL is required when QDRANT_MODE is set to 'remote'.")
    elif settings.qdrant_mode == "local":
        if not settings.qdrant_path:
            raise ValueError("Qdrant configuration error: QDRANT_PATH is required when QDRANT_MODE is set to 'local'.")

    if settings.langsmith_tracing and not settings.langsmith_api_key:
        raise ValueError("LangSmith configuration error: LANGSMITH_API_KEY is required when LANGSMITH_TRACING is enabled.")

    if settings.google_auth_enabled:
        if not settings.google_client_id or not settings.google_client_secret or not settings.google_redirect_uri:
            raise ValueError("Google auth configuration error: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI are required when GOOGLE_AUTH_ENABLED is true.")
        if not settings.google_redirect_uri.startswith(("http://", "https://")):
            raise ValueError("Google auth configuration error: GOOGLE_REDIRECT_URI must be an absolute HTTP(S) URL.")

    if settings.email_provider == "smtp":
        if not settings.smtp_host or not settings.smtp_username or not settings.smtp_password or not settings.email_from_address:
            raise ValueError("SMTP email configuration error: SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, and EMAIL_FROM_ADDRESS are required when EMAIL_PROVIDER is set to 'smtp'.")
    elif settings.email_provider == "resend":
        if not settings.resend_api_key or not settings.email_from_address:
            raise ValueError("Resend email configuration error: RESEND_API_KEY and EMAIL_FROM_ADDRESS (or EMAIL_FROM) are required when EMAIL_PROVIDER is set to 'resend'.")
    elif settings.email_provider == "console":
        pass
    else:
        raise ValueError(f"Invalid EMAIL_PROVIDER: '{settings.email_provider}'. Must be one of 'console', 'smtp', or 'resend'.")

    if settings.vector_size < 1 or settings.event_batch_max_size > 50 or settings.mesh_total_budget_seconds < 1:
        raise ValueError("Invalid vector or event limits")

    if settings.recommendation_final_count < 1 or settings.recommendation_final_count > settings.recommendation_max_candidates:
        raise ValueError("Recommendation configuration error: recommendation_final_count must be positive and <= recommendation_max_candidates.")

    if settings.payments_mode != "demo":
        raise ValueError("Only demo payments are enabled in this phase")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
