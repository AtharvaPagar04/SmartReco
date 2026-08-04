from openai import AsyncOpenAI

from app.config import settings


class MeshConfigurationError(RuntimeError):
    pass


def mesh_client() -> AsyncOpenAI:
    if not settings.mesh_api_key:
        raise MeshConfigurationError("Mesh API key is not configured")
    return AsyncOpenAI(base_url=settings.mesh_base_url, api_key=settings.mesh_api_key, timeout=settings.mesh_request_timeout_seconds, max_retries=settings.mesh_max_retries)
