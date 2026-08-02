from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.services.vector_sync_service import process_pending_vector_jobs


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(process_pending_vector_jobs, IntervalTrigger(seconds=settings.vector_sync_interval_seconds), id="vector-sync", max_instances=1, coalesce=True, misfire_grace_time=60)
    return scheduler
