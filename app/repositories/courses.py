from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course


async def public_by_slug(db: AsyncSession, slug: str) -> Course | None:
    return await db.scalar(select(Course).where(Course.slug == slug, Course.is_active.is_(True)))
