from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.services.vector_sync_service import process_pending_vector_jobs
from app.jobs.recommendation_jobs import process_email_deliveries, queue_daily_digests, recover_recommendation_runs, scan_recommendation_eligibility


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(process_pending_vector_jobs, IntervalTrigger(seconds=settings.vector_sync_interval_seconds), id="vector-sync", max_instances=1, coalesce=True, misfire_grace_time=60)
    scheduler.add_job(scan_recommendation_eligibility, IntervalTrigger(seconds=300), id="recommendation-eligibility", max_instances=1, coalesce=True, misfire_grace_time=120)
    scheduler.add_job(recover_recommendation_runs, IntervalTrigger(seconds=300), id="recommendation-recovery", max_instances=1, coalesce=True, misfire_grace_time=120)
    scheduler.add_job(queue_daily_digests, IntervalTrigger(seconds=3600), id="recommendation-digests", max_instances=1, coalesce=True, misfire_grace_time=300)
    scheduler.add_job(process_email_deliveries, IntervalTrigger(seconds=300), id="recommendation-email-delivery", max_instances=1, coalesce=True, misfire_grace_time=120)
    return scheduler
