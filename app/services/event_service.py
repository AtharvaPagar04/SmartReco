from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.models import ActivityEvent, Course
from app.services.recommendation_policy_service import mark_user_dirty
from app.schemas.event import EventInput


def server_session_id(session: dict) -> str:
    value = session.get("session_id")
    if not value:
        value = uuid4().hex
        session["session_id"] = value
    return value


async def ingest_events(db: AsyncSession, events: list[tuple[int, EventInput]], *, user_id: str | None, session_id: str) -> tuple[int, int, list[dict]]:
    accepted, duplicates, errors = 0, 0, []
    rows: list[tuple[int, ActivityEvent]] = []
    seen: set[str] = set()
    supplied_ids = [event.event_id for _, event in events if event.event_id]
    existing_ids = set()
    if supplied_ids:
        existing_ids = set((await db.scalars(select(ActivityEvent.event_id).where(ActivityEvent.event_id.in_(supplied_ids)))).all())
    for index, event in events:
        if len(str(event.metadata).encode()) > settings.event_metadata_max_bytes:
            errors.append({"index": index, "code": "metadata_too_large"})
            continue
        if event.course_id:
            try:
                UUID(event.course_id)
            except ValueError:
                errors.append({"index": index, "code": "invalid_course_id"})
                continue
            if not await db.scalar(select(Course.id).where(Course.id == event.course_id)):
                errors.append({"index": index, "code": "course_not_found"})
                continue
        if event.event_type in {"COURSE_IMPRESSION", "COURSE_VIEW", "COURSE_CLICK", "RECOMMENDATION_IMPRESSION", "RECOMMENDATION_CLICK"} and not event.course_id:
            errors.append({"index": index, "code": "course_id_required"})
            continue
        if event.event_type == "SEARCH" and not event.normalized_search():
            errors.append({"index": index, "code": "empty_search_query"})
            continue
        if event.event_type == "DWELL" and event.page_path and event.page_path.startswith("/courses/") and not event.course_id:
            errors.append({"index": index, "code": "course_id_required"})
            continue
        occurred = event.normalized_time()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if occurred > now.replace(tzinfo=None):
            occurred = now
        if (now - occurred).days > 90:
            errors.append({"index": index, "code": "event_too_old"})
            continue
        event_id = event.event_id or str(uuid4())
        if event_id in existing_ids or event_id in seen:
            duplicates += 1
            continue
        seen.add(event_id)
        rows.append((index, ActivityEvent(event_id=event_id, schema_version=event.schema_version, user_id=user_id, session_id=session_id, event_type=event.event_type, course_id=event.course_id, search_query=event.normalized_search(), page_path=event.page_path, metadata_json=event.metadata, duration_ms=event.duration_ms, occurred_at=occurred, received_at=now)))
    for _, row in rows:
        try:
            async with db.begin_nested():
                db.add(row)
                await db.flush()
            accepted += 1
        except IntegrityError:
            duplicates += 1
    if rows:
        if user_id and any(row.event_type in {"SEARCH", "COURSE_CLICK", "COURSE_VIEW", "DWELL", "FILTER_CHANGE", "RECOMMENDATION_CLICK", "RECOMMENDATION_DISMISS"} for _, row in rows):
            await mark_user_dirty(db, user_id, occurred_at=max((row.occurred_at for _, row in rows), default=None))
        await db.commit()
    return accepted, duplicates, errors
