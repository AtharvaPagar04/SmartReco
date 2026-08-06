from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ActivityEvent, Course, CourseEntitlement, Enrollment, RecommendationItem, UserInterestProfile
from app.repositories.recommendation_feedback import feedback_preferences_for_user

MEANINGFUL_EVENTS = {"SEARCH", "COURSE_CLICK", "COURSE_VIEW", "DWELL", "FILTER_CHANGE", "RECOMMENDATION_CLICK", "RECOMMENDATION_DISMISS", "RECOMMENDATION_REJECTED", "LEARNING_PATH_GENERATED", "LEARNING_PATH_SAVED", "LEARNING_PATH_COURSE_REPLACED", "LEARNING_PATH_ARCHIVED"}
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.-]*", re.I)


def _to_naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _decay(occurred_at: datetime, now: datetime) -> float:
    dt_occurred = _to_naive(occurred_at) or _now()
    dt_now = _to_naive(now) or _now()
    age = max(0.0, (dt_now - dt_occurred).total_seconds() / 86400)
    return 0.5 ** (age / max(1, settings.recommendation_signal_half_life_days))



def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in TOKEN_RE.findall(value or "") if len(token) > 1}


def _clean_search(value: str | None) -> str:
    return " ".join((value or "").split())[:200]


def _hash_profile(profile: dict) -> str:
    canonical = {
        "top_categories": profile.get("top_categories", []),
        "top_tags": profile.get("top_tags", []),
        "top_search_terms": profile.get("top_search_terms", []),
        "engaged_course_ids": profile.get("engaged_course_ids", []),
        "recent_course_ids": profile.get("recent_course_ids", []),
        "excluded_course_ids": profile.get("excluded_course_ids", []),
        "completed_course_ids": profile.get("completed_course_ids", []),
        "enrolled_course_ids": profile.get("enrolled_course_ids", []),
        "purchased_unstarted_course_ids": profile.get("purchased_unstarted_course_ids", []),
        "recently_viewed_course_ids": profile.get("recently_viewed_course_ids", []),
        "continued_course_ids": profile.get("continued_course_ids", []),
        "dismissed_course_ids": profile.get("dismissed_course_ids", []),
        "recommendation_feedback": profile.get("recommendation_feedback", {}),
        "confidence": profile.get("confidence", 0.0),
    }
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()



def _add_score(target: dict[str, dict], name: str, score: float, evidence_count: int = 1) -> None:
    key = " ".join(name.split())
    if not key:
        return
    entry = target.setdefault(key.casefold(), {"name": key, "score": 0.0, "evidence_count": 0})
    entry["score"] += score
    entry["evidence_count"] += evidence_count


def _ranked(target: dict[str, dict], limit: int = 8) -> list[dict]:
    values = list(target.values())
    maximum = max((entry["score"] for entry in values), default=0.0) or 1.0
    for entry in values:
        entry["score"] = round(min(1.0, entry["score"] / maximum), 4)
    return sorted(values, key=lambda item: (-item["score"], item["name"].casefold()))[:limit]


@dataclass(frozen=True)
class ProfileSnapshot:
    profile: dict
    profile_hash: str
    event_count: int
    max_occurred_at: datetime | None


async def _snapshot(db: AsyncSession, user_id: str) -> ProfileSnapshot:
    now = _now()
    start = now - timedelta(days=settings.recommendation_event_window_days)
    events = list((await db.execute(
        select(ActivityEvent, Course)
        .outerjoin(Course, Course.id == ActivityEvent.course_id)
        .where(ActivityEvent.user_id == user_id, ActivityEvent.occurred_at >= start)
        .order_by(ActivityEvent.occurred_at.desc(), ActivityEvent.id.desc())
        .limit(5000)
    )).all())
    categories: dict[str, dict] = {}
    tags: dict[str, dict] = {}
    searches: dict[str, dict] = {}
    engaged: dict[str, tuple[float, datetime]] = {}
    recent: list[str] = []
    sessions: set[str] = set()
    dwell_seconds = 0
    counts = {"searches": 0, "course_clicks": 0, "course_views": 0, "qualified_impressions": 0, "dwell_seconds": 0}
    for event, course in events:
        if event.event_type not in MEANINGFUL_EVENTS and event.event_type != "COURSE_IMPRESSION":
            continue
        decay = _decay(event.occurred_at, now)
        sessions.add(event.session_id)
        if event.event_type == "COURSE_IMPRESSION":
            counts["qualified_impressions"] += 1
            if course:
                _add_score(categories, course.category, 0.5 * decay)
            continue
        if event.event_type == "SEARCH":
            query = _clean_search(event.search_query)
            if len(query) >= 2 and not set(query) <= set("!?.,:;<>/\\"):
                counts["searches"] += 1
                key = query.casefold()
                if key not in searches:
                    searches[key] = {"term": query, "score": 0.0, "searched_at": event.occurred_at.isoformat()}
                searches[key]["score"] += 5.0 * decay
                for known in categories:
                    if known.casefold() in key:
                        _add_score(categories, known, 2.0 * decay)
        elif event.event_type == "COURSE_CLICK":
            counts["course_clicks"] += 1
        elif event.event_type == "COURSE_VIEW":
            counts["course_views"] += 1
        elif event.event_type == "DWELL":
            duration = min(max(event.duration_ms or 0, 0), 30 * 60 * 1000) / 1000
            if duration >= 5:
                dwell_seconds += int(duration)
                counts["dwell_seconds"] += int(duration)
        if course and event.event_type in {"COURSE_CLICK", "COURSE_VIEW", "DWELL", "RECOMMENDATION_CLICK"}:
            weight = {"COURSE_CLICK": 4.0, "COURSE_VIEW": 3.0, "DWELL": min(8.0, max(0.0, (event.duration_ms or 0) / 30000)), "RECOMMENDATION_CLICK": 5.0}.get(event.event_type, 1.0)
            score = weight * decay
            _add_score(categories, course.category, score)
            for tag in course.tags or []:
                _add_score(tags, str(tag), score)
            previous = engaged.get(course.id)
            if not previous or score > previous[0]:
                engaged[course.id] = (score, event.occurred_at)
            if course.id not in recent:
                recent.append(course.id)
    dismissed_ids = list((await db.scalars(select(RecommendationItem.course_id).where(RecommendationItem.user_id == user_id, RecommendationItem.dismissed_at.is_not(None)))).all())
    enrollment_rows = list((await db.execute(select(Enrollment, Course).join(Course, Course.id == Enrollment.course_id).where(Enrollment.user_id == user_id))).all())
    completed_ids = [enrollment.course_id for enrollment, _ in enrollment_rows if enrollment.completed_at or enrollment.status.upper() == "COMPLETED"]
    enrolled_ids = [enrollment.course_id for enrollment, _ in enrollment_rows if enrollment.course_id not in completed_ids]
    continued_ids = [enrollment.course_id for enrollment, _ in enrollment_rows if enrollment.course_id in enrolled_ids and enrollment.last_accessed_at and enrollment.started_at and (_to_naive(enrollment.last_accessed_at) > _to_naive(enrollment.started_at))]
    entitlement_ids = list((await db.scalars(select(CourseEntitlement.course_id).where(CourseEntitlement.user_id == user_id, CourseEntitlement.revoked_at.is_(None)))).all())
    feedback = await feedback_preferences_for_user(db, user_id=user_id)
    purchased_unstarted_ids = [course_id for course_id in entitlement_ids if course_id not in {enrollment.course_id for enrollment, _ in enrollment_rows}]
    excluded = list(dict.fromkeys([*enrolled_ids, *completed_ids, *entitlement_ids, *dismissed_ids, *feedback.excluded_course_ids]))[:50]
    course_summary = lambda course: {"course_id": course.id, "title": course.title, "category": course.category, "difficulty": course.difficulty, "tags": list(course.tags or [])[:6]}
    completed_courses = [course_summary(course) for enrollment, course in enrollment_rows if enrollment.course_id in completed_ids][:5]
    enrolled_courses = [course_summary(course) for enrollment, course in enrollment_rows if enrollment.course_id in enrolled_ids][:5]
    recently_viewed_courses = []
    courses_by_id = {course.id: course for _, course in enrollment_rows}
    if recent:
        recent_rows = list((await db.scalars(select(Course).where(Course.id.in_(recent), Course.is_active.is_(True)))).all())
        courses_by_id.update({course.id: course for course in recent_rows})
        recently_viewed_courses = [course_summary(courses_by_id[course_id]) for course_id in recent if course_id in courses_by_id][:5]
    meaningful = sum(counts.values()) - counts["qualified_impressions"]
    distinct_courses = len(engaged)
    confidence = min(1.0, 0.15 * min(4, meaningful) + 0.1 * min(3, distinct_courses) + 0.1 * min(2, len(searches)) + (0.2 if dwell_seconds >= 30 else 0))
    profile = {
        "profile_version": 1,
        "top_categories": _ranked(categories),
        "top_tags": _ranked(tags),
        "top_search_terms": sorted(searches.values(), key=lambda item: (-item["score"], item["term"].casefold()))[:8],
        "engaged_course_ids": [item[0] for item in sorted(engaged.items(), key=lambda item: (-item[1][0], item[0]))[:8]],
        "recent_course_ids": recent[:8],
        "excluded_course_ids": excluded,
        "completed_course_ids": completed_ids[:50],
        "enrolled_course_ids": enrolled_ids[:50],
        "purchased_unstarted_course_ids": purchased_unstarted_ids[:50],
        "recently_viewed_course_ids": recent[:50],
        "continued_course_ids": continued_ids[:50],
        "dismissed_course_ids": dismissed_ids[:50],
        "recommendation_feedback": feedback.to_profile_dict(),
        "completed_courses": completed_courses,
        "enrolled_courses": enrolled_courses,
        "recently_viewed_courses": recently_viewed_courses,
        "signal_summary": counts,
        "confidence": round(min(1.0, confidence), 4),
        "distinct_sessions": len(sessions),
    }
    max_event = max((event.occurred_at for event, _ in events), default=None)
    return ProfileSnapshot(profile, _hash_profile(profile), len(events), max_event)


async def build_or_refresh_profile(db: AsyncSession, user_id: str, *, force: bool = False) -> UserInterestProfile:
    snapshot = await _snapshot(db, user_id)
    current = await db.scalar(select(UserInterestProfile).where(UserInterestProfile.user_id == user_id))
    now = _now()
    if current:
        if current.profile_hash != snapshot.profile_hash:
            current.version += 1
            current.profile_hash = snapshot.profile_hash
        current.profile_json = snapshot.profile
        current.source_event_count = snapshot.event_count
        current.source_event_max_occurred_at = snapshot.max_occurred_at
        current.window_started_at = now - timedelta(days=settings.recommendation_event_window_days)
        current.window_ended_at = now
        current.generated_at = now
        await db.flush()
        return current
    current = UserInterestProfile(
        user_id=user_id,
        version=1,
        profile_hash=snapshot.profile_hash,
        profile_json=snapshot.profile,
        source_event_count=snapshot.event_count,
        source_event_max_occurred_at=snapshot.max_occurred_at,
        window_started_at=now - timedelta(days=settings.recommendation_event_window_days),
        window_ended_at=now,
        generated_at=now,
    )
    db.add(current)
    await db.flush()
    return current
