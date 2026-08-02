from openai import AsyncOpenAI

from app.config import settings


class MeshConfigurationError(RuntimeError):
    pass


def mesh_client() -> AsyncOpenAI:
    if not settings.mesh_api_key:
        raise MeshConfigurationError("Mesh API key is not configured")
    return AsyncOpenAI(base_url="https://api.meshapi.ai/v1", api_key=settings.mesh_api_key, timeout=30)
