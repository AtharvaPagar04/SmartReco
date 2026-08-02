from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_maker
from app.models import Course, VectorOutbox
from app.services.embedding_service import embed_course
from app.services.mesh_client import MeshConfigurationError
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)
BACKOFF = (30, 120, 600, 1800, 3600)


async def recover_stale(db: AsyncSession) -> None:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=settings.vector_processing_timeout_seconds)
    await db.execute(update(VectorOutbox).where(VectorOutbox.status == "PROCESSING", VectorOutbox.processing_started_at < cutoff, VectorOutbox.attempts < settings.vector_sync_max_attempts).values(status="PENDING", processing_started_at=None))
    await db.execute(update(VectorOutbox).where(VectorOutbox.status == "PROCESSING", VectorOutbox.processing_started_at < cutoff, VectorOutbox.attempts >= settings.vector_sync_max_attempts).values(status="FAILED", last_error="Processing timeout after maximum attempts", processing_started_at=None))
    await db.commit()


async def claim_jobs(db: AsyncSession) -> list[str]:
    await recover_stale(db)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    eligible = and_(VectorOutbox.status == "PENDING", or_(VectorOutbox.next_attempt_at <= now, VectorOutbox.next_attempt_at.is_(None)))
    query = select(VectorOutbox).where(eligible, VectorOutbox.attempts < settings.vector_sync_max_attempts).order_by(VectorOutbox.created_at).limit(settings.vector_sync_batch_size)
    if not settings.database_url.startswith("sqlite"):
        query = query.with_for_update(skip_locked=True)
    rows = list((await db.execute(query)).scalars())
    for row in rows:
        row.status = "PROCESSING"
        row.processing_started_at = now
        row.attempts += 1
    return [row.id for row in rows]


async def process_one_job(outbox_id: str) -> None:
    async with async_session_maker() as db:
        job = await db.get(VectorOutbox, outbox_id)
        if not job or job.status not in {"PROCESSING", "PENDING"}:
            return
        course = await db.get(Course, job.course_id)
        if (job.operation == "UPSERT" and not course) or (course and course.version != job.course_version):
            job.status = "SUPERSEDED"
            job.processed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await db.commit()
            return
        if job.operation == "UPSERT" and (job.embedding_model != settings.mesh_embedding_model or job.embedding_dimension != settings.vector_size or job.embedding_schema_version != settings.embedding_schema_version):
            job.status = "SUPERSEDED"
            job.processed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            if course:
                course.vector_status = "PENDING"
                db.add(VectorOutbox(course_id=course.id, operation="UPSERT", course_version=course.version, payload=course.vector_payload(), embedding_model=settings.mesh_embedding_model, embedding_dimension=settings.vector_size, embedding_schema_version=settings.embedding_schema_version))
            await db.commit()
            return
        try:
            store = VectorStore()
            await store.ensure_collection()
            if job.operation == "DELETE":
                await store.delete(job.course_id)
                if course:
                    course.vector_status = "NOT_INDEXED"
                    course.indexed_embedding_model = None
                    course.indexed_embedding_dimension = None
                    course.indexed_embedding_schema_version = None
            else:
                vector = await embed_course(course)
                lineage = {"embedding_model": job.embedding_model, "embedding_dimension": len(vector), "embedding_schema_version": job.embedding_schema_version, "embedded_at": datetime.now(timezone.utc).isoformat()}
                await store.upsert(vector, course.vector_payload(lineage=lineage))
                course.vector_status = "SYNCED"
                course.vector_last_synced_at = datetime.now(timezone.utc).replace(tzinfo=None)
                course.indexed_embedding_model = job.embedding_model
                course.indexed_embedding_dimension = len(vector)
                course.indexed_embedding_schema_version = job.embedding_schema_version
            job.status = "DONE"
            job.processed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            job.last_error = None
        except MeshConfigurationError as exc:
            job.status = "FAILED"
            job.last_error = str(exc)
            if course:
                course.vector_status = "FAILED"
        except Exception as exc:
            job.last_error = str(exc)[:500]
            if job.attempts >= settings.vector_sync_max_attempts:
                job.status = "FAILED"
                if course:
                    course.vector_status = "FAILED"
            else:
                job.status = "PENDING"
                job.next_attempt_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=BACKOFF[min(job.attempts - 1, len(BACKOFF) - 1)])
            logger.warning("vector job failed", extra={"outbox_id": outbox_id, "attempt": job.attempts})
        await db.commit()


async def process_pending_vector_jobs() -> None:
    async with async_session_maker() as db:
        ids = await claim_jobs(db)
        await db.commit()
    for outbox_id in ids:
        await process_one_job(outbox_id)
