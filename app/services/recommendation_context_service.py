from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActivityEvent, Course, CourseEntitlement, Enrollment, UserInterestProfile


def _course(course: Course) -> dict:
    return {
        "id": course.id,
        "slug": course.slug,
        "title": course.title,
        "category": course.category,
        "difficulty": course.difficulty,
        "tags": list(course.tags or []),
        "tools_used": list(getattr(course, "tools_used", None) or []),
        "what_you_will_learn": list(getattr(course, "what_you_will_learn", None) or []),
    }


async def build_learning_context(db: AsyncSession, user_id: str, profile: dict | None = None) -> dict:
    if profile is None:
        row = await db.scalar(select(UserInterestProfile).where(UserInterestProfile.user_id == user_id))
        profile = row.profile_json if row else {}
    enrollments = list((await db.execute(select(Enrollment, Course).join(Course, Course.id == Enrollment.course_id).where(Enrollment.user_id == user_id, Course.is_active.is_(True)))).all())
    completed_ids = {enrollment.course_id for enrollment, _ in enrollments if enrollment.completed_at or enrollment.status.upper() == "COMPLETED"}
    enrolled = [_course(course) for enrollment, course in enrollments if enrollment.course_id not in completed_ids][:5]
    completed = [_course(course) for enrollment, course in enrollments if enrollment.course_id in completed_ids][:5]
    enrolled_ids = {enrollment.course_id for enrollment, _ in enrollments}

    completed_skills = []
    seen_skills = set()
    for item in completed:
        for skill in item.get("tools_used", []) + item.get("tags", []):
            if skill and skill.strip() and skill.strip().lower() not in seen_skills:
                seen_skills.add(skill.strip().lower())
                completed_skills.append(skill.strip())

    entitlements = list((await db.execute(
        select(CourseEntitlement, Course)
        .join(Course, Course.id == CourseEntitlement.course_id)
        .where(CourseEntitlement.user_id == user_id, CourseEntitlement.revoked_at.is_(None), Course.is_active.is_(True))
    )).all())
    ready = [_course(course) for entitlement, course in entitlements if entitlement.course_id not in enrolled_ids][:5]

    viewed_rows = list((await db.execute(
        select(ActivityEvent, Course)
        .join(Course, Course.id == ActivityEvent.course_id)
        .where(
            ActivityEvent.user_id == user_id,
            ActivityEvent.event_type.in_(("COURSE_VIEW", "COURSE_CLICK", "DWELL", "COURSE_IMPRESSION", "RECOMMENDATION_CLICK")),
            Course.is_active.is_(True),
        )
        .order_by(ActivityEvent.occurred_at.desc(), ActivityEvent.id.desc())
        .limit(30)
    )).all())
    explored = []
    seen = set(enrolled_ids) | completed_ids
    for _, course in viewed_rows:
        if course.id not in seen and course.id not in {item["id"] for item in explored}:
            explored.append(_course(course))
        if len(explored) == 5:
            break
    if not explored and profile:
        recent_ids = profile.get("recently_viewed_course_ids", profile.get("recent_course_ids", []))
        recent_courses = list((await db.scalars(select(Course).where(Course.id.in_(recent_ids), Course.is_active.is_(True)))).all()) if recent_ids else []
        by_id = {course.id: course for course in recent_courses}
        explored = [_course(by_id[course_id]) for course_id in recent_ids if course_id in by_id and course_id not in seen][:5]

    direction = "practical learning"
    if profile:
        direction = (profile.get("top_categories") or [{"name": "practical learning"}])[0].get("name", direction)
    return {
        "enrolled": enrolled,
        "completed": completed,
        "completed_skills": completed_skills,
        "recently_explored": explored,
        "ready_to_start": ready,
        "learning_direction": direction,
    }
