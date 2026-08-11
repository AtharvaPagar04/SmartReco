from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import RecommendationItem, RecommendationPreference, RecommendationRun


async def current_for_user(db: AsyncSession, user_id: str) -> RecommendationRun | None:
    return await db.scalar(
        select(RecommendationRun)
        .options(selectinload(RecommendationRun.items).selectinload(RecommendationItem.course))
        .where(RecommendationRun.user_id == user_id, RecommendationRun.status.in_(("SUCCEEDED", "FALLBACK_SUCCEEDED")))
        .order_by(RecommendationRun.created_at.desc(), RecommendationRun.id.desc())
        .limit(1)
    )


async def get_or_create_recommendation_preference(db: AsyncSession, user_id: str) -> RecommendationPreference:
    pref = await db.get(RecommendationPreference, user_id)
    if not pref:
        pref = RecommendationPreference(
            user_id=user_id,
            recommendations_enabled=True,
            session_followup_email_enabled=True,
        )
        db.add(pref)
        try:
            await db.commit()
            await db.refresh(pref)
        except IntegrityError:
            await db.rollback()
            pref = await db.get(RecommendationPreference, user_id)
    return pref
