from datetime import datetime, timedelta, timezone
import pytest
from qdrant_client import QdrantClient

from app.config import settings
from app.models import VectorOutbox
from app.services.vector_store import VectorStore
import app.services.vector_sync_service as sync_service
from app.services.vector_sync_service import claim_jobs, process_one_job, process_pending_vector_jobs, recover_stale
from app.repositories.vector_outbox import create as create_outbox
from tests.conftest import csrf


@pytest.mark.asyncio
async def test_sqlite_claim_marks_jobs_processing(db_session, course):
    job = VectorOutbox(
        course_id=course.id,
        operation="UPSERT",
        course_version=course.version,
        payload=course.vector_payload(),
        status="PENDING",
        next_attempt_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=5),
    )
    db_session.add(job)
    await db_session.commit()
    ids = await claim_jobs(db_session)
    await db_session.commit()
    assert ids == [job.id]
    assert job.status == "PROCESSING"
    assert job.attempts == 1


@pytest.mark.asyncio
async def test_outbox_versioning_and_superseded(db_session, course):
    job1 = VectorOutbox(
        course_id=course.id,
        operation="UPSERT",
        course_version=1,
        payload=course.vector_payload(),
        status="PENDING",
        next_attempt_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=5),
    )
    db_session.add(job1)
    await db_session.commit()

    # Increment course version to 2
    course.version = 2
    await db_session.commit()

    # Process job1 which has course_version=1
    await process_one_job(job1.id)

    await db_session.commit()
    await db_session.refresh(job1)
    assert job1.status == "SUPERSEDED"
    assert job1.processed_at is not None


@pytest.mark.asyncio
async def test_stale_processing_recovery_and_retries(client, db_session, admin_user, course):
    stale_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=settings.vector_processing_timeout_seconds + 10)

    # Job 1: stale PROCESSING with 1 attempt (should reset to PENDING)
    job_recoverable = VectorOutbox(
        course_id=course.id,
        operation="UPSERT",
        course_version=course.version,
        status="PROCESSING",
        processing_started_at=stale_time,
        next_attempt_at=stale_time,
        attempts=1,
    )

    # Job 2: stale PROCESSING with max attempts (should fail)
    job_exhausted = VectorOutbox(
        course_id=course.id,
        operation="UPSERT",
        course_version=course.version,
        status="PROCESSING",
        processing_started_at=stale_time,
        next_attempt_at=stale_time,
        attempts=settings.vector_sync_max_attempts,
    )

    db_session.add_all([job_recoverable, job_exhausted])
    await db_session.commit()

    await recover_stale(db_session)

    await db_session.commit()
    await db_session.refresh(job_recoverable)
    await db_session.refresh(job_exhausted)

    assert job_recoverable.status == "PENDING"
    assert job_recoverable.processing_started_at is None

    assert job_exhausted.status == "FAILED"
    assert "timeout" in job_exhausted.last_error.lower()

    # Admin retry of job_exhausted
    client.cookies.clear()
    login = await client.get("/login")
    login_res = await client.post("/login", data={"email": admin_user.email, "password": "AdminPass123!", "csrf_token": csrf(login.text)})
    assert login_res.status_code == 303

    vector_sync_page = await client.get("/admin/vector-sync")
    retry_res = await client.post(f"/admin/vector-sync/{job_exhausted.id}/retry", data={"csrf_token": csrf(vector_sync_page.text)})
    assert retry_res.status_code == 303

    await db_session.commit()
    await db_session.refresh(job_exhausted)
    assert job_exhausted.status == "PENDING"
    assert job_exhausted.attempts == 0


@pytest.mark.asyncio
async def test_qdrant_vector_store_upsert_and_delete(tmp_path, monkeypatch, course):
    monkeypatch.setattr(settings, "qdrant_mode", "local")
    monkeypatch.setattr(settings, "qdrant_path", str(tmp_path / "qdrant"))
    monkeypatch.setattr(settings, "qdrant_collection", "smartreco_courses_test_unit")

    store = VectorStore()
    await store.ensure_collection()

    # Test dimension validation
    with pytest.raises(ValueError):
        await store.upsert([0.1 + i * 0.0001 for i in range(10)], course.vector_payload())

    fake_vector = [0.1 + i * 0.0001 for i in range(settings.vector_size)]
    payload = course.vector_payload()
    await store.upsert(fake_vector, payload)

    hits = await store.search_courses(fake_vector, limit=5)
    assert len(hits) == 1
    assert hits[0].course_id == course.id

    await store.delete(course.id)

    hits_after = await store.search_courses(fake_vector, limit=5)
    assert len(hits_after) == 0


@pytest.mark.asyncio
async def test_scheduler_jobs_create_fresh_async_sessions(db_session, course, monkeypatch):
    async def fake_embed(_course):
        return [0.1 + i * 0.0001 for i in range(settings.vector_size)]

    monkeypatch.setattr(sync_service, "embed_course", fake_embed)

    job = VectorOutbox(
        course_id=course.id,
        operation="UPSERT",
        course_version=course.version,
        status="PENDING",
        next_attempt_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=5),
    )
    db_session.add(job)
    await db_session.commit()

    # Call process_pending_vector_jobs directly, which spawns fresh AsyncSession contexts
    await process_pending_vector_jobs()

    db_session.expire_all()
    await db_session.refresh(job)
    assert job.status in {"DONE", "FAILED", "SUPERSEDED"}


@pytest.mark.asyncio
async def test_outbox_captures_embedding_lineage(db_session, course):
    job = create_outbox(course, "UPSERT", datetime.now(timezone.utc).replace(tzinfo=None))
    db_session.add(job)
    await db_session.commit()
    assert job.embedding_model == settings.mesh_embedding_model
    assert job.embedding_dimension == settings.vector_size
    assert job.embedding_schema_version == settings.embedding_schema_version


@pytest.mark.asyncio
async def test_successful_sync_persists_lineage(db_session, course, monkeypatch):
    captured = {}

    class FakeStore:
        async def ensure_collection(self):
            return None

        async def upsert(self, vector, payload):
            captured["payload"] = payload

        async def delete(self, course_id):
            return None

    async def fake_embed(_course):
        return [0.1 + i * 0.0001 for i in range(settings.vector_size)]

    monkeypatch.setattr(sync_service, "VectorStore", FakeStore)
    monkeypatch.setattr(sync_service, "embed_course", fake_embed)
    job = create_outbox(course, "UPSERT", datetime.now(timezone.utc).replace(tzinfo=None))
    db_session.add(job)
    await db_session.commit()
    await process_one_job(job.id)
    await db_session.refresh(course)
    assert course.vector_status == "SYNCED"
    assert course.indexed_embedding_model == settings.mesh_embedding_model
    assert captured["payload"]["embedding_dimension"] == settings.vector_size
    assert captured["payload"]["embedding_schema_version"] == settings.embedding_schema_version


@pytest.mark.asyncio
async def test_qdrant_isolation_regression_prevents_dev_collection_contamination(db_session, course):
    dev_client = QdrantClient(path="./data/qdrant")
    initial_dev_count = 0
    try:
        initial_dev_count = dev_client.count("smartreco_courses").count
    except Exception:
        pass

    assert settings.qdrant_path != "./data/qdrant"
    assert "smartreco_courses_test_" in settings.qdrant_collection
    assert settings.qdrant_collection != "smartreco_courses"

    store = VectorStore()
    await store.ensure_collection()
    fake_vector = [0.1 + i * 0.0001 for i in range(settings.vector_size)]
    await store.upsert(fake_vector, course.vector_payload())

    hits = await store.search_courses(fake_vector, limit=5)
    assert len(hits) == 1
    assert hits[0].course_id == course.id

    final_dev_count = 0
    try:
        final_dev_count = dev_client.count("smartreco_courses").count
    except Exception:
        pass

    assert final_dev_count == initial_dev_count
