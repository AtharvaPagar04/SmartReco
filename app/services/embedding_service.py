from app.models import Course
from app.services.mesh_client import mesh_client


async def embed_course(course: Course) -> list[float]:
    response = await mesh_client().embeddings.create(model=__import__("app.config", fromlist=["settings"]).settings.mesh_embedding_model, input=[course.embedding_text()])
    try:
        vector = response.data[0].embedding
    except (AttributeError, IndexError) as exc:
        raise RuntimeError("Mesh returned no embedding") from exc
    if not isinstance(vector, list) or not vector or not all(isinstance(x, (int, float)) for x in vector):
        raise RuntimeError("Mesh returned an invalid embedding")
    return [float(x) for x in vector]
