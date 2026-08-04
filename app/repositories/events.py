from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActivityEvent, Course
from app.search import normalize_search_query


@dataclass
class ViewedCourse:
    title: str
    slug: str
    category: str
    is_active: bool
    last_viewed_at: datetime
    dwell_minutes: int


@dataclass
class AccountActivity:
    recently_viewed_courses: list[ViewedCourse]
    recent_searches: list[dict]
    categories_explored: list[dict]
    weekly: dict
    last_active_at: datetime | None


async def recent_for_user(db: AsyncSession, user_id: str, limit: int = 20) -> list[ActivityEvent]:
    return list((await db.execute(select(ActivityEvent).where(ActivityEvent.user_id == user_id).order_by(ActivityEvent.occurred_at.desc()).limit(limit))).scalars())


async def recent_searches_for_user(db: AsyncSession, user_id: str, limit: int = 6) -> list[dict]:
    rows = (await db.execute(
        select(ActivityEvent.search_query, ActivityEvent.occurred_at)
        .where(ActivityEvent.user_id == user_id, ActivityEvent.event_type == "SEARCH", ActivityEvent.search_query.is_not(None))
        .order_by(ActivityEvent.occurred_at.desc(), ActivityEvent.id.desc())
        .limit(max(12, limit * 8))
    )).all()
    recent: list[dict] = []
    seen: set[str] = set()
    for query, searched_at in rows:
        normalized = normalize_search_query(query)
        key = normalized.casefold()
        if len(normalized) < 2 or key in seen:
            continue
        seen.add(key)
        recent.append({"query": normalized, "searched_at": searched_at.replace(tzinfo=timezone.utc) if searched_at.tzinfo is None else searched_at})
        if len(recent) >= limit:
            break
    return recent


async def account_activity(db: AsyncSession, user_id: str) -> AccountActivity:
    meaningful = ("COURSE_VIEW", "COURSE_CLICK", "DWELL")
    dwell_minutes = func.coalesce(func.sum(case((ActivityEvent.event_type == "DWELL", ActivityEvent.duration_ms), else_=0)), 0)
    viewed_rows = (await db.execute(
        select(Course.title, Course.slug, Course.category, Course.is_active, func.max(ActivityEvent.occurred_at), dwell_minutes)
        .join(Course, Course.id == ActivityEvent.course_id)
        .where(ActivityEvent.user_id == user_id, ActivityEvent.event_type.in_(meaningful), ActivityEvent.course_id.is_not(None))
        .group_by(Course.id)
        .order_by(func.max(ActivityEvent.occurred_at).desc(), Course.id)
        .limit(8)
    )).all()
    viewed = [ViewedCourse(title=row[0], slug=row[1], category=row[2], is_active=row[3], last_viewed_at=row[4], dwell_minutes=round((row[5] or 0) / 60000)) for row in viewed_rows]

    recent_searches = await recent_searches_for_user(db, user_id, limit=8)

    categories = (await db.execute(
        select(Course.category, func.count(func.distinct(Course.id))).select_from(ActivityEvent)
        .join(Course, Course.id == ActivityEvent.course_id)
        .where(ActivityEvent.user_id == user_id, ActivityEvent.event_type.in_(meaningful), ActivityEvent.course_id.is_not(None))
        .group_by(Course.category)
        .order_by(func.count(func.distinct(Course.id)).desc(), Course.category)
        .limit(8)
    )).all()
    categories_explored = [{"category": row[0], "count": row[1]} for row in categories]

    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
    weekly = {
        "courses_viewed": await db.scalar(select(func.count(func.distinct(ActivityEvent.course_id))).where(ActivityEvent.user_id == user_id, ActivityEvent.event_type.in_(meaningful), ActivityEvent.course_id.is_not(None), ActivityEvent.occurred_at >= since)),
        "searches": await db.scalar(select(func.count(ActivityEvent.id)).where(ActivityEvent.user_id == user_id, ActivityEvent.event_type == "SEARCH", ActivityEvent.occurred_at >= since)),
        "dwell_minutes": round((await db.scalar(select(func.coalesce(func.sum(ActivityEvent.duration_ms), 0)).where(ActivityEvent.user_id == user_id, ActivityEvent.event_type == "DWELL", ActivityEvent.occurred_at >= since)) or 0) / 60000),
    }
    last_active = await db.scalar(select(func.max(ActivityEvent.occurred_at)).where(ActivityEvent.user_id == user_id))
    return AccountActivity(viewed, recent_searches, categories_explored, weekly, last_active)


async def recent_viewed_for_session(db: AsyncSession, session_id: str) -> list[ViewedCourse]:
    meaningful = ("COURSE_VIEW", "COURSE_CLICK", "DWELL")
    dwell_minutes = func.coalesce(func.sum(case((ActivityEvent.event_type == "DWELL", ActivityEvent.duration_ms), else_=0)), 0)
    viewed_rows = (await db.execute(
        select(Course.title, Course.slug, Course.category, Course.is_active, func.max(ActivityEvent.occurred_at), dwell_minutes)
        .join(Course, Course.id == ActivityEvent.course_id)
        .where(ActivityEvent.session_id == session_id, ActivityEvent.event_type.in_(meaningful), ActivityEvent.course_id.is_not(None))
        .group_by(Course.id)
        .order_by(func.max(ActivityEvent.occurred_at).desc(), Course.id)
        .limit(8)
    )).all()
    return [ViewedCourse(title=row[0], slug=row[1], category=row[2], is_active=row[3], last_viewed_at=row[4], dwell_minutes=round((row[5] or 0) / 60000)) for row in viewed_rows]

