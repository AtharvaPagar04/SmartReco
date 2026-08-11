from datetime import datetime, timedelta, timezone
import logging
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import async_session_maker
from app.models import RecommendationDelivery, RecommendationItem, RecommendationPreference, RecommendationRun, RecommendationState, SessionFollowupState, User
from app.repositories.recommendations import current_for_user
from app.services.recommendation_email_service import email_provider, render_digest
from app.services.recommendation_service import generate_recommendation

logger = logging.getLogger(__name__)


async def scan_recommendation_eligibility() -> None:
    async with async_session_maker() as db:
        user_ids = list((await db.scalars(select(RecommendationState.user_id).where(RecommendationState.dirty_since.is_not(None)).order_by(RecommendationState.dirty_since).limit(10))).all())
    for user_id in user_ids:
        async with async_session_maker() as db:
            try:
                await generate_recommendation(db, user_id)
            except Exception:
                await db.rollback()


async def recover_recommendation_runs() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with async_session_maker() as db:
        states = list((await db.scalars(select(RecommendationState).where(RecommendationState.lease_expires_at < now))).all())
        for state in states:
            if state.active_run_id:
                run = await db.get(RecommendationRun, state.active_run_id)
                if run and run.status == "RUNNING":
                    run.status = "FAILED"
                    run.error_code = "lease_expired"
                    run.error_message = "Recommendation worker lease expired"
                    run.completed_at = now
            state.active_run_id = None
            state.lease_expires_at = None
        await db.commit()


async def queue_daily_digests() -> None:
    now = datetime.now(timezone.utc)
    async with async_session_maker() as db:
        preferences = list((await db.scalars(select(RecommendationPreference).where(RecommendationPreference.email_digest_enabled.is_(True)).limit(50))).all())
        for preference in preferences:
            try:
                local = now.astimezone(ZoneInfo(preference.timezone))
            except Exception:
                local = now
            local_date = local.date().isoformat()
            if local.hour < preference.digest_hour_local or preference.last_digest_local_date == local_date:
                continue
            run = await current_for_user(db, preference.user_id)
            if not run:
                continue
            existing = await db.scalar(select(RecommendationDelivery.id).where(RecommendationDelivery.user_id == preference.user_id, RecommendationDelivery.scheduled_for >= datetime.combine(local.date(), datetime.min.time()), RecommendationDelivery.status.in_(("PENDING", "SENDING", "SENT"))))
            if not existing:
                user = await db.get(User, preference.user_id)
                if user:
                    db.add(RecommendationDelivery(run_id=run.id, user_id=user.id, recipient=user.email, scheduled_for=now.replace(tzinfo=None)))
            preference.last_digest_local_date = local_date
        await db.commit()


async def process_email_deliveries() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with async_session_maker() as db:
        deliveries = list((await db.scalars(select(RecommendationDelivery).where(RecommendationDelivery.status == "PENDING", (RecommendationDelivery.next_attempt_at.is_(None)) | (RecommendationDelivery.next_attempt_at <= now)).order_by(RecommendationDelivery.scheduled_for).limit(10))).all())
        for delivery in deliveries:
            delivery.status = "SENDING"
            delivery.attempts += 1
        await db.commit()
    for delivery_id in [delivery.id for delivery in deliveries]:
        async with async_session_maker() as db:
            delivery = await db.get(RecommendationDelivery, delivery_id)
            run = await db.scalar(select(RecommendationRun).options(selectinload(RecommendationRun.items).selectinload(RecommendationItem.course)).where(RecommendationRun.id == delivery.run_id)) if delivery else None
            if not delivery or not run:
                continue
            text, html = render_digest(run)
            result = await email_provider().send_recommendation_digest(recipient=delivery.recipient, subject=run.headline or "Your SmartReco learning path", text=text, html=html)
            followup_state = await db.scalar(
                select(SessionFollowupState).where(
                    (SessionFollowupState.recommendation_delivery_id == delivery.id)
                    | (SessionFollowupState.recommendation_run_id == run.id)
                )
            )
            if result.success:
                delivery.status = "SENT"
                delivery.sent_at = now
                delivery.provider_message_id = result.message_id
                if followup_state:
                    followup_state.status = "SENT"
                    followup_state.completed_at = now
                logger.info("session_followup.delivery.sent", extra={"delivery_id": delivery.id, "provider": settings.email_provider or "console"})
            elif delivery.attempts >= 5 or result.permanent:
                delivery.status = "FAILED"
                delivery.error_code = "email_delivery_failed"
                delivery.error_message = (result.error or "delivery failed")[:500]
                if followup_state:
                    followup_state.status = "FAILED"
                    followup_state.completed_at = now
                    followup_state.error_code = delivery.error_code
                    followup_state.error_message = delivery.error_message
                logger.warning("session_followup.delivery.failed_permanent", extra={"delivery_id": delivery.id, "error": delivery.error_message})
            else:
                delivery.status = "PENDING"
                delivery.error_code = "email_delivery_failed"
                delivery.error_message = (result.error or "delivery failed")[:500]
                delivery.next_attempt_at = now + timedelta(minutes=min(60, 2 ** delivery.attempts))
            await db.commit()
