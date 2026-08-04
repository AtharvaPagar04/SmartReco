from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ActivityEvent, RecommendationFeedback, RecommendationRun, RecommendationState, UserInterestProfile


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True)
class RecommendationDecision:
    eligible: bool
    reason: str
    trigger_type: str | None = None
    next_eligible_at: datetime | None = None


async def mark_user_dirty(db: AsyncSession, user_id: str, *, occurred_at: datetime | None = None, immediate: bool = False) -> None:
    state = await db.get(RecommendationState, user_id)
    if not state:
        state = RecommendationState(user_id=user_id)
        db.add(state)
    state.dirty_since = state.dirty_since or occurred_at or now_utc()
    if immediate:
        state.cooldown_until = None
    await db.flush()


async def decide(db: AsyncSession, user_id: str, *, trigger_type: str = "BEHAVIOR_THRESHOLD", force: bool = False) -> RecommendationDecision:
    if not settings.recommendations_enabled:
        return RecommendationDecision(False, "RECOMMENDATIONS_DISABLED")
    state = await db.get(RecommendationState, user_id)
    if not state and not force:
        return RecommendationDecision(False, "INSUFFICIENT_ACTIVITY")
    if not state and force:
        return RecommendationDecision(True, "FORCED", trigger_type)
    now = now_utc()
    if state.active_run_id and state.lease_expires_at and state.lease_expires_at > now:
        return RecommendationDecision(False, "RUN_ALREADY_ACTIVE")
    if state.next_retry_at and state.next_retry_at > now:
        return RecommendationDecision(False, "RETRY_BACKOFF", next_eligible_at=state.next_retry_at)
    if not force:
        latest_feedback = await db.scalar(
            select(func.max(RecommendationFeedback.created_at)).where(RecommendationFeedback.user_id == user_id)
        )
        if latest_feedback and state.dirty_since and (not state.last_recommendation_at or latest_feedback > state.last_recommendation_at):
            return RecommendationDecision(True, "FEEDBACK_REPLACEMENT", trigger_type)
    if state.cooldown_until and state.cooldown_until > now and not force:
        return RecommendationDecision(False, "COOLDOWN_ACTIVE", next_eligible_at=state.cooldown_until)
    if not force:
        since = state.last_profiled_event_at or now - timedelta(days=settings.recommendation_event_window_days)
        meaningful = await db.scalar(select(func.count(ActivityEvent.id)).where(ActivityEvent.user_id == user_id, ActivityEvent.occurred_at > since, ActivityEvent.event_type.in_(("SEARCH", "COURSE_CLICK", "COURSE_VIEW", "DWELL", "FILTER_CHANGE", "RECOMMENDATION_CLICK", "RECOMMENDATION_DISMISS")))) or 0
        dwell = await db.scalar(select(func.coalesce(func.sum(ActivityEvent.duration_ms), 0)).where(ActivityEvent.user_id == user_id, ActivityEvent.occurred_at > since, ActivityEvent.event_type == "DWELL")) or 0
        searches = await db.scalar(select(func.count(ActivityEvent.id)).where(ActivityEvent.user_id == user_id, ActivityEvent.occurred_at > since, ActivityEvent.event_type == "SEARCH")) or 0
        if meaningful < settings.recommendation_min_meaningful_events and not (searches >= 1 and meaningful >= 2) and dwell < 60000:
            return RecommendationDecision(False, "INSUFFICIENT_ACTIVITY")
        latest = await db.scalar(select(RecommendationRun).where(RecommendationRun.user_id == user_id, RecommendationRun.status.in_(("SUCCEEDED", "FALLBACK_SUCCEEDED"))).order_by(RecommendationRun.created_at.desc()).limit(1))
        profile = await db.scalar(select(UserInterestProfile).where(UserInterestProfile.user_id == user_id))
        if latest and profile and latest.created_at and latest.created_at >= now - timedelta(hours=settings.recommendation_ttl_hours) and latest.profile_hash == profile.profile_hash and state.dirty_since is None:
            return RecommendationDecision(False, "FRESH_RECOMMENDATION_EXISTS")
    return RecommendationDecision(True, "ELIGIBLE_BEHAVIOR_CHANGE" if trigger_type == "BEHAVIOR_THRESHOLD" else trigger_type, trigger_type)
