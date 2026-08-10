import uuid
import pytest
from app.config import settings
from app.services.vector_store import VectorStore
from scripts.reconcile_vectors import reconcile


@pytest.mark.asyncio
async def test_reconcile_orphan_deletion_and_protection(db_session, course, monkeypatch):
    store = VectorStore()
    await store.ensure_collection()

    # 1. Insert a healthy point for the active SQL course
    healthy_vector = [0.1 + i * 0.0001 for i in range(settings.vector_size)]
    lineage = {
        "embedding_model": settings.mesh_embedding_model,
        "embedding_dimension": settings.vector_size,
        "embedding_schema_version": settings.embedding_schema_version,
    }
    healthy_payload = course.vector_payload(lineage=lineage)
    await store.upsert(healthy_vector, healthy_payload)

    # 2. Insert an orphan point with no matching SQL course
    orphan_id = str(uuid.uuid4())
    orphan_vector = [0.2 + i * 0.0001 for i in range(settings.vector_size)]
    orphan_payload = {
        "course_id": orphan_id,
        "title": "Orphan Test Course",
        "slug": "orphan-test-course",
        "category": "Testing",
        "difficulty": "BEGINNER",
        "price": 0.0,
        "currency": "USD",
        "tags": ["test"],
        "instructor": "Test Instructor",
        "duration_minutes": 60,
        "is_active": True,
        "version": 1,
        "embedding_model": settings.mesh_embedding_model,
        "embedding_dimension": settings.vector_size,
        "embedding_schema_version": settings.embedding_schema_version,
    }
    await store.upsert(orphan_vector, orphan_payload)
    store.close()

    # Verify initial state via dry-run
    dry_run_counts = await reconcile(dry_run=True, repair=False)
    assert dry_run_counts["healthy"] == 1
    assert dry_run_counts["orphan_vector"] == 1

    # Execute repair
    repair_counts = await reconcile(dry_run=False, repair=True)
    assert repair_counts["orphans_deleted"] == 1
    assert repair_counts["repairs_failed"] == 0
    assert repair_counts["repairs_attempted"] == 1

    # Verify orphan is deleted from Qdrant
    check_store = VectorStore()
    deleted_point = await check_store.get_point(orphan_id)
    assert deleted_point is None

    # Verify healthy point is preserved in Qdrant
    healthy_point = await check_store.get_point(course.id)
    assert healthy_point is not None
    assert healthy_point.payload["course_id"] == course.id
    check_store.close()

    # Verify idempotency on repeated repair
    idempotent_counts = await reconcile(dry_run=False, repair=True)
    assert idempotent_counts["orphan_vector"] == 0
    assert idempotent_counts["orphans_deleted"] == 0
    assert idempotent_counts["repairs_failed"] == 0


@pytest.mark.asyncio
async def test_reconcile_failed_deletion_reporting(db_session, monkeypatch):
    store = VectorStore()
    await store.ensure_collection()

    orphan_id = str(uuid.uuid4())
    orphan_vector = [0.1 + i * 0.0001 for i in range(settings.vector_size)]
    await store.upsert(orphan_vector, {"course_id": orphan_id, "version": 1, "is_active": True, "embedding_model": settings.mesh_embedding_model, "embedding_dimension": settings.vector_size, "embedding_schema_version": settings.embedding_schema_version})
    store.close()

    async def failing_delete(self, point_id):
        raise RuntimeError("Qdrant write error mock")

    monkeypatch.setattr(VectorStore, "delete", failing_delete)

    counts = await reconcile(dry_run=False, repair=True)
    assert counts["orphan_vector"] == 1
    assert counts["repairs_failed"] == 1
    assert counts["orphans_deleted"] == 0
