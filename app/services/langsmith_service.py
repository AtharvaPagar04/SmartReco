import os
from app.config import settings


def tracing_enabled() -> bool:
    enabled = bool(settings.langsmith_tracing and settings.langsmith_api_key)
    if enabled:
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project or "smartreco"
        os.environ["LANGSMITH_ENDPOINT"] = getattr(settings, "langsmith_endpoint", "https://api.smith.langchain.com")
    return enabled


def trace_metadata(*, user_id: str, trigger_type: str, profile_version: int, candidate_count: int) -> dict:
    return {"user_ref": user_id[:8], "trigger_type": trigger_type, "profile_version": profile_version, "candidate_count": candidate_count}
