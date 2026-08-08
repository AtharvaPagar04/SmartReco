import os
from pathlib import Path
import tomllib
from typing import Any

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"

SUPPORTED_ENVS = {"development", "production", "test", "staging"}

TOML_TO_SETTINGS: dict[tuple[str, str], str] = {
    ("app", "name"): "app_name",
    ("app", "debug"): "debug",
    ("app", "base_url"): "app_base_url",
    ("app", "timezone"): "app_timezone",
    ("app", "log_level"): "log_level",

    ("mesh", "base_url"): "mesh_base_url",
    ("mesh", "embedding_model"): "mesh_embedding_model",
    ("mesh", "chat_model"): "mesh_chat_model",
    ("mesh", "request_timeout_seconds"): "mesh_request_timeout_seconds",
    ("mesh", "max_retries"): "mesh_max_retries",
    ("mesh", "total_budget_seconds"): "mesh_total_budget_seconds",

    ("embedding", "schema_version"): "embedding_schema_version",

    ("related_courses", "enabled"): "related_courses_enabled",
    ("related_courses", "limit"): "related_courses_limit",
    ("related_courses", "candidate_limit"): "related_courses_candidate_limit",
    ("related_courses", "cache_ttl_seconds"): "related_courses_cache_ttl_seconds",
    ("related_courses", "semantic_weight"): "related_courses_semantic_weight",
    ("related_courses", "category_weight"): "related_courses_category_weight",
    ("related_courses", "tag_weight"): "related_courses_tag_weight",
    ("related_courses", "difficulty_weight"): "related_courses_difficulty_weight",
    ("related_courses", "timeout_seconds"): "related_courses_timeout_seconds",

    ("qdrant", "mode"): "qdrant_mode",
    ("qdrant", "path"): "qdrant_path",
    ("qdrant", "collection"): "qdrant_collection",
    ("qdrant", "vector_size"): "vector_size",

    ("vector_sync", "interval_seconds"): "vector_sync_interval_seconds",
    ("vector_sync", "batch_size"): "vector_sync_batch_size",
    ("vector_sync", "max_attempts"): "vector_sync_max_attempts",
    ("vector_sync", "processing_timeout_seconds"): "vector_processing_timeout_seconds",

    ("events", "batch_max_size"): "event_batch_max_size",
    ("events", "metadata_max_bytes"): "event_metadata_max_bytes",
    ("events", "queue_max_size"): "event_queue_max_size",

    ("session", "cookie_name"): "session_cookie_name",
    ("session", "https_only"): "session_https_only",
    ("session", "max_age_seconds"): "session_max_age_seconds",

    ("admin", "email"): "admin_email",

    ("recommendations", "enabled"): "recommendations_enabled",
    ("recommendations", "event_window_days"): "recommendation_event_window_days",
    ("recommendations", "signal_half_life_days"): "recommendation_signal_half_life_days",
    ("recommendations", "min_meaningful_events"): "recommendation_min_meaningful_events",
    ("recommendations", "min_signal_score"): "recommendation_min_signal_score",
    ("recommendations", "cooldown_minutes"): "recommendation_cooldown_minutes",
    ("recommendations", "ttl_hours"): "recommendation_ttl_hours",
    ("recommendations", "max_candidates"): "recommendation_max_candidates",
    ("recommendations", "final_count"): "recommendation_final_count",
    ("recommendations", "display_limit"): "recommendation_display_limit",
    ("recommendations", "max_refinements"): "recommendation_max_refinements",
    ("recommendations", "job_batch_size"): "recommendation_job_batch_size",
    ("recommendations", "lease_minutes"): "recommendation_lease_minutes",

    ("learning_path", "builder_enabled"): "learning_path_builder_enabled",
    ("learning_path", "chat_model"): "learning_path_chat_model",
    ("learning_path", "prompt_version"): "learning_path_prompt_version",
    ("learning_path", "max_candidates"): "learning_path_max_candidates",
    ("learning_path", "max_courses"): "learning_path_max_courses",
    ("learning_path", "max_repairs"): "learning_path_max_repairs",

    ("langsmith", "tracing"): "langsmith_tracing",
    ("langsmith", "project"): "langsmith_project",
    ("langsmith", "endpoint"): "langsmith_endpoint",

    ("email", "provider"): "email_provider",
    ("email", "from_name"): "email_from_name",
    ("email", "from_address"): "email_from_address",
    ("email", "smtp_port"): "smtp_port",
    ("email", "smtp_use_tls"): "smtp_use_tls",

    ("google_auth", "enabled"): "google_auth_enabled",
    ("google_auth", "oidc_discovery_url"): "google_oidc_discovery_url",
    ("google_auth", "oauth_state_ttl_seconds"): "google_oauth_state_ttl_seconds",
    ("google_auth", "request_timeout_seconds"): "google_request_timeout_seconds",

    ("commerce", "payments_enabled"): "payments_enabled",
    ("commerce", "payments_mode"): "payments_mode",
    ("commerce", "cart_max_items"): "cart_max_items",
    ("commerce", "default_currency"): "default_currency",
}


def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and key in target and isinstance(target[key], dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value


def load_toml_dict(file_path: Path) -> dict[str, Any]:
    if not file_path.exists():
        return {}
    try:
        with file_path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Malformed TOML file at {file_path}: {exc}") from exc


def load_toml_settings(*, config_dir: Path | None = None, app_env: str | None = None) -> dict[str, Any]:
    if config_dir is None:
        config_dir = CONFIG_DIR
    if app_env is None:
        app_env = os.getenv("APP_ENV", "development").lower()
    else:
        app_env = app_env.lower()

    if app_env not in SUPPORTED_ENVS:
        raise ValueError(f"Unsupported APP_ENV: '{app_env}'. Must be one of {sorted(SUPPORTED_ENVS)}.")

    merged_toml: dict[str, Any] = {}

    defaults_file = config_dir / "defaults.toml"
    _deep_merge(merged_toml, load_toml_dict(defaults_file))

    env_file = config_dir / f"{app_env}.toml"
    _deep_merge(merged_toml, load_toml_dict(env_file))

    if app_env == "development":
        local_file = config_dir / "local.toml"
        if local_file.exists():
            _deep_merge(merged_toml, load_toml_dict(local_file))

    flat_settings: dict[str, Any] = {}
    for (section, key), setting_attr in TOML_TO_SETTINGS.items():
        if section in merged_toml and key in merged_toml[section]:
            flat_settings[setting_attr] = merged_toml[section][key]

    return flat_settings


class TomlConfigSettingsSource(PydanticBaseSettingsSource):
    def __init__(self, settings_cls: type[BaseSettings], config_dir: Path | None = None):
        super().__init__(settings_cls)
        self.config_dir = config_dir or CONFIG_DIR

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        app_env = os.getenv("APP_ENV", "development")
        return load_toml_settings(config_dir=self.config_dir, app_env=app_env)
