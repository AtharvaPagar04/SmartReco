import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.csrf import validate_csrf_token
from app.database import get_db
from app.dependencies import get_user
from app.flash import flash
from app.models import Course, CourseEntitlement, Enrollment, User
from app.repositories.enrollments import complete_enrollment, course_ids_for_user, courses_for_user, enrollment_for_user, touch_enrollment
from app.repositories.courses import public_by_slug
from app.routers.helpers import page
from app.security import current_user
from app.services.catalog_service import categories, list_courses
from app.services.recommendation_policy_service import mark_user_dirty
from app.services.related_course_service import get_related_courses
from app.services.course_action_service import load_course_actions, user_access_course_ids

router = APIRouter()
logger = logging.getLogger(__name__)



def _related_view(item) -> dict:
    course = item.course
    return {
        "id": course.id,
        "slug": course.slug,
        "title": course.title,
        "short_description": course.short_description,
        "category": course.category,
        "difficulty": course.difficulty,
        "price": str(course.price),
        "currency": course.currency,
        "tags": [str(tag) for tag in (course.tags or [])[:2]],
        "duration_minutes": course.duration_minutes,
        "thumbnail_url": course.thumbnail_url,
        "source": item.source,
        "enrolled": False,
    }


@router.get("/")
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    user = await current_user(request, db)
    enrolled_course_ids = await course_ids_for_user(db, user.id) if user else set()
    access_course_ids = await user_access_course_ids(db, user.id) if user else set()
    filters = [Course.is_active.is_(True), Course.is_featured.is_(True)]
    if access_course_ids:
        filters.append(Course.id.not_in(access_course_ids))
    featured = list((await db.execute(select(Course).where(*filters).order_by(Course.created_at.desc()).limit(6))).scalars())
    learning = await courses_for_user(db, user.id) if user else []
    action_states = await load_course_actions(db, [*featured, *learning], user.id if user else None)
    return page(request, "home.html", current_user=user, featured=featured, learning=learning, enrolled_course_ids=enrolled_course_ids, action_states=action_states, categories=await categories(db))


@router.get("/courses")
async def course_catalog(request: Request, q: str = Query("", max_length=200), category: str = Query("", max_length=80), difficulty: str = Query("", max_length=20), price: str = Query("", max_length=10), sort: str = Query("newest", max_length=20), page_number: int = Query(1, alias="page", ge=1), size: int = Query(12, ge=1, le=24), db: AsyncSession = Depends(get_db)):
    user = await current_user(request, db)
    courses, total, page_number, size = await list_courses(db, query=q, category=category, difficulty=difficulty, price=price, sort=sort, page=page_number, size=size)
    enrolled_course_ids = await course_ids_for_user(db, user.id) if user else set()
    action_states = await load_course_actions(db, courses, user.id if user else None)
    return page(request, "catalog/list.html", current_user=user, courses=courses, enrolled_course_ids=enrolled_course_ids, action_states=action_states, total=total, page=page_number, size=size, pages=(total + size - 1) // size, q=q, category=category, difficulty=difficulty, price=price, sort=sort, categories=await categories(db))


@router.post("/courses/{slug}/enroll")
async def enroll(slug: str, request: Request, user: User = Depends(get_user), db: AsyncSession = Depends(get_db), csrf_token: str = Form("")):
    validate_csrf_token(request, csrf_token)
    course = await public_by_slug(db, slug)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    entitlement = await db.scalar(select(CourseEntitlement).where(CourseEntitlement.user_id == user.id, CourseEntitlement.course_id == course.id))
    if course.price > 0 and not (entitlement and entitlement.revoked_at is None):
        existing = await enrollment_for_user(db, user.id, course.id)
        if not existing:
            flash(request, "Purchase this course before starting it.", "warning")
            return RedirectResponse(f"/courses/{course.slug}", status_code=303)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    enrollment = await enrollment_for_user(db, user.id, course.id)
    if enrollment:
        touch_enrollment(enrollment, now)
    else:
        try:
            async with db.begin_nested():
                if entitlement and entitlement.revoked_at is not None:
                    entitlement.revoked_at = None
                    entitlement.source = "FREE"
                    entitlement.granted_at = now
                elif not entitlement:
                    db.add(CourseEntitlement(user_id=user.id, course_id=course.id, source="FREE", granted_at=now))
                db.add(Enrollment(user_id=user.id, course_id=course.id, started_at=now, last_accessed_at=now))
                await db.flush()
        except IntegrityError:
            enrollment = await enrollment_for_user(db, user.id, course.id)
            if enrollment:
                touch_enrollment(enrollment, now)
            else:
                raise
    await mark_user_dirty(db, user.id, occurred_at=now)
    await db.commit()
    return RedirectResponse(f"/courses/{course.slug}", status_code=303)


@router.post("/courses/{slug}/complete")
async def complete_course(slug: str, request: Request, user: User = Depends(get_user), db: AsyncSession = Depends(get_db), csrf_token: str = Form("")):
    validate_csrf_token(request, csrf_token)
    course = await public_by_slug(db, slug)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    enrollment = await enrollment_for_user(db, user.id, course.id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if not enrollment:
        entitlement = await db.scalar(select(CourseEntitlement).where(CourseEntitlement.user_id == user.id, CourseEntitlement.course_id == course.id))
        if course.price > 0 and not (entitlement and entitlement.revoked_at is None):
            flash(request, "Purchase this course before marking it complete.", "warning")
            return RedirectResponse(f"/courses/{course.slug}", status_code=303)
        enrollment = Enrollment(user_id=user.id, course_id=course.id, started_at=now, last_accessed_at=now)
        db.add(enrollment)
        await db.flush()
    complete_enrollment(enrollment, now)
    await mark_user_dirty(db, user.id, occurred_at=now)
    await db.commit()
    flash(request, f"Congratulations! You completed '{course.title}'!", "success")
    return RedirectResponse(f"/courses/{course.slug}", status_code=303)



@router.get("/courses/{slug}")
async def course_detail(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    course = await public_by_slug(db, slug)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    user = await current_user(request, db)
    enrolled_course_ids = await course_ids_for_user(db, user.id) if user else set()
    access_course_ids = await user_access_course_ids(db, user.id) if user else set()
    enrollment = await enrollment_for_user(db, user.id, course.id) if user else None
    if enrollment:
        touch_enrollment(enrollment, datetime.now(timezone.utc).replace(tzinfo=None))
        await db.commit()
    try:
        related = await get_related_courses(db, course, limit=2, excluded_course_ids=access_course_ids)
        related_actions = await load_course_actions(db, [item.course for item in related], user.id if user else None)
        related_courses = [{**_related_view(item), "enrolled": item.course.id in enrolled_course_ids, "action": related_actions[item.course.id], "rank": rank} for rank, item in enumerate(related, 1)]
    except Exception as exc:
        logger.info("contextual related-course lookup failed", extra={"course_id": course.id, "error_category": type(exc).__name__})
        related_courses = []
    action = (await load_course_actions(db, [course], user.id if user else None))[course.id]
    return page(request, "catalog/detail.html", current_user=user, course=course, enrolled_course_ids=enrolled_course_ids, action=action, related_courses=related_courses)
