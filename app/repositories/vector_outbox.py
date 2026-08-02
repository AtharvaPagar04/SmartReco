from datetime import datetime

from app.config import settings
from app.models import Course, VectorOutbox


def create(course: Course, operation: str, now: datetime) -> VectorOutbox:
    return VectorOutbox(
        course_id=course.id,
        operation=operation,
        course_version=course.version,
        payload=course.vector_payload(),
        embedding_model=settings.mesh_embedding_model,
        embedding_dimension=settings.vector_size,
        embedding_schema_version=settings.embedding_schema_version,
        next_attempt_at=now,
    )
