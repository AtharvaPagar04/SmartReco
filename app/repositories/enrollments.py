from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course, Enrollment


async def course_ids_for_user(db: AsyncSession, user_id: str) -> set[str]:
    return set((await db.scalars(select(Enrollment.course_id).where(Enrollment.user_id == user_id))).all())


async def courses_for_user(db: AsyncSession, user_id: str, *, limit: int = 6) -> list[Course]:
    return list((await db.scalars(
        select(Course)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .where(Enrollment.user_id == user_id, Course.is_active.is_(True))
        .order_by(func.coalesce(Enrollment.last_accessed_at, Enrollment.started_at).desc(), Course.id.asc())
        .limit(limit)
    )).all())


async def enrollment_for_user(db: AsyncSession, user_id: str, course_id: str) -> Enrollment | None:
    return await db.scalar(select(Enrollment).where(Enrollment.user_id == user_id, Enrollment.course_id == course_id))


def touch_enrollment(enrollment: Enrollment, now: datetime) -> None:
    enrollment.last_accessed_at = now


def complete_enrollment(enrollment: Enrollment, now: datetime) -> None:
    enrollment.status = "COMPLETED"
    enrollment.completed_at = now
    enrollment.last_accessed_at = now
