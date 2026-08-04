import asyncio
from dataclasses import dataclass

from qdrant_client import QdrantClient, models

from app.config import settings


@dataclass
class VectorCourseHit:
    course_id: str
    score: float
    payload: dict


class VectorStore:
    def __init__(self):
        self.kwargs = {"path": settings.qdrant_path} if settings.qdrant_mode == "local" else {"url": settings.qdrant_url, "api_key": settings.qdrant_api_key or None}
        self.client = None

    def _get_client(self) -> QdrantClient:
        if self.client is None:
            self.client = QdrantClient(**self.kwargs)
        return self.client

    async def ensure_collection(self) -> None:
        def _do():
            client = self._get_client()
            names = {item.name for item in client.get_collections().collections}
            if settings.qdrant_collection not in names:
                client.create_collection(settings.qdrant_collection, vectors_config=models.VectorParams(size=settings.vector_size, distance=models.Distance.COSINE))
                for field, schema in (("category", models.PayloadSchemaType.KEYWORD), ("difficulty", models.PayloadSchemaType.KEYWORD), ("is_active", models.PayloadSchemaType.BOOL), ("version", models.PayloadSchemaType.INTEGER)):
                    client.create_payload_index(settings.qdrant_collection, field, schema)
        await asyncio.to_thread(_do)

    async def upsert(self, vector: list[float], payload: dict) -> None:
        if len(vector) != settings.vector_size:
            raise ValueError(f"Embedding dimension {len(vector)} does not match VECTOR_SIZE {settings.vector_size}")

        def _do():
            client = self._get_client()
            client.upsert(collection_name=settings.qdrant_collection, points=[models.PointStruct(id=payload["course_id"], vector=vector, payload=payload)], wait=True)
        await asyncio.to_thread(_do)

    async def delete(self, course_id: str) -> None:
        def _do():
            client = self._get_client()
            client.delete(collection_name=settings.qdrant_collection, points_selector=[course_id], wait=True)
        await asyncio.to_thread(_do)

    async def get_point(self, course_id: str, *, with_vectors: bool = False):
        def _do():
            client = self._get_client()
            points = client.retrieve(collection_name=settings.qdrant_collection, ids=[course_id], with_payload=True, with_vectors=with_vectors)
            return points[0] if points else None
        return await asyncio.to_thread(_do)

    async def scroll_points(self, *, limit: int = 100):
        def _do():
            client = self._get_client()
            points, offset = [], None
            while True:
                batch, offset = client.scroll(collection_name=settings.qdrant_collection, limit=limit, offset=offset, with_payload=True, with_vectors=False)
                points.extend(batch)
                if offset is None:
                    return points
        return await asyncio.to_thread(_do)

    async def search_courses(self, query_vector: list[float], *, limit: int, filters: dict | None = None) -> list[VectorCourseHit]:
        def _do():
            client = self._get_client()
            query_filter = None
            if filters:
                conditions = []
                for field, value in filters.items():
                    if field == "embedding_dimension":
                        field = "embedding_dimension"
                    conditions.append(models.FieldCondition(key=field, match=models.MatchValue(value=value)))
                query_filter = models.Filter(must=conditions)
            result = client.search(collection_name=settings.qdrant_collection, query_vector=query_vector, limit=limit, query_filter=query_filter)
            return [VectorCourseHit(str(hit.id), hit.score, hit.payload or {}) for hit in result]
        return await asyncio.to_thread(_do)

    def close(self) -> None:
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None
