from app.config import settings


def tracing_enabled() -> bool:
    return bool(settings.langsmith_tracing and settings.langsmith_api_key)


def trace_metadata(*, user_id: str, trigger_type: str, profile_version: int, candidate_count: int) -> dict:
    return {"user_ref": user_id[:8], "trigger_type": trigger_type, "profile_version": profile_version, "candidate_count": candidate_count}
