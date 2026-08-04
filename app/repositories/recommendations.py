from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import RecommendationItem, RecommendationRun


async def current_for_user(db: AsyncSession, user_id: str) -> RecommendationRun | None:
    return await db.scalar(
        select(RecommendationRun)
        .options(selectinload(RecommendationRun.items).selectinload(RecommendationItem.course))
        .where(RecommendationRun.user_id == user_id, RecommendationRun.status.in_(("SUCCEEDED", "FALLBACK_SUCCEEDED")))
        .order_by(RecommendationRun.created_at.desc(), RecommendationRun.id.desc())
        .limit(1)
    )
