from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from slugify import slugify
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.constants import COURSE_CATEGORIES, DIFFICULTIES
from app.csrf import validate_csrf_token
from app.database import get_db
from app.dependencies import get_admin
from app.flash import flash
from app.models import ActivityEvent, Course, RecommendationFeedback, RecommendationItem, RecommendationRun, User, VectorOutbox
from app.routers.helpers import page
from app.schemas.course import CourseForm
from app.repositories.vector_outbox import create as create_outbox
from app.services.event_service import server_session_id
from app.security import safe_next
from app.services.catalog_service import VECTOR_FIELDS, apply_course_record

router = APIRouter(prefix="/admin")


class FormBacking:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        if isinstance(getattr(self, "tags", None), str):
            self.tags = [t.strip() for t in self.tags.split(",") if t.strip()]
        if getattr(self, "thumbnail_url", None) is None:
            self.thumbnail_url = ""


def _form(**values):
    try:
        return CourseForm(**values), []
    except ValidationError as exc:
        errors = [err.get("msg", str(err)).removeprefix("Value error, ") for err in exc.errors()]
        return None, errors
    except ValueError as exc:
        return None, [str(exc)]


def _values(title, slug, short_description, description, category, tags, price, currency, difficulty, instructor, duration_minutes, thumbnail_url, is_featured, is_active):
    return dict(
        title=title,
        slug=slug or None,
        short_description=short_description,
        description=description,
        category=category,
        tags=tags,
        price=price,
        currency=currency,
        difficulty=difficulty,
        instructor=instructor,
        duration_minutes=duration_minutes,
        thumbnail_url=thumbnail_url or None,
        is_featured=is_featured,
        is_active=is_active,
    )


def _outbox(course: Course, operation: str) -> VectorOutbox:
    return create_outbox(course, operation, datetime.now(timezone.utc).replace(tzinfo=None))


@router.get("")
async def dashboard(request: Request, admin: User = Depends(get_admin), db: AsyncSession = Depends(get_db)):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    counts = {
        "users": await db.scalar(select(func.count(User.id))),
        "active_courses": await db.scalar(select(func.count(Course.id)).where(Course.is_active.is_(True))),
        "inactive_courses": await db.scalar(select(func.count(Course.id)).where(Course.is_active.is_(False))),
        "events_today": await db.scalar(select(func.count(ActivityEvent.id)).where(ActivityEvent.received_at >= today)),
        "pending": await db.scalar(select(func.count(VectorOutbox.id)).where(VectorOutbox.status == "PENDING")),
        "processing": await db.scalar(select(func.count(VectorOutbox.id)).where(VectorOutbox.status == "PROCESSING")),
        "failed": await db.scalar(select(func.count(VectorOutbox.id)).where(VectorOutbox.status == "FAILED")),
        "synced": await db.scalar(select(func.count(Course.id)).where(Course.vector_status == "SYNCED")),
    }
    return page(request, "admin/dashboard.html", current_user=admin, counts=counts)


@router.get("/courses")
async def courses(request: Request, q: str = Query("", max_length=200), active: str = Query("", max_length=5), vector_status: str = Query("", max_length=20), sort: str = Query("recently_updated", max_length=30), page_number: int = Query(1, alias="page", ge=1), page_size: int = Query(20, ge=1, le=100), db: AsyncSession = Depends(get_db), admin: User = Depends(get_admin)):
    sort = sort if sort in {"newest", "oldest", "title", "recently_updated"} else "recently_updated"
    filters = []
    if q:
        filters.append(Course.title.ilike(f"%{' '.join(q.split())}%"))
    if active in {"true", "false"}:
        filters.append(Course.is_active.is_(active == "true"))
    if vector_status:
        filters.append(Course.vector_status == vector_status)
    order = {
        "newest": (Course.created_at.desc(), Course.id),
        "oldest": (Course.created_at, Course.id),
        "title": (Course.title, Course.id),
        "recently_updated": (Course.updated_at.desc(), Course.id),
    }[sort]
    total = await db.scalar(select(func.count(Course.id)).where(*filters)) or 0
    pages = max(1, (total + page_size - 1) // page_size)
    page_number = min(page_number, pages)
    items = list((await db.execute(select(Course).where(*filters).order_by(*order).limit(page_size).offset((page_number - 1) * page_size))).scalars())
    list_url = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    return page(request, "admin/courses.html", current_user=admin, courses=items, q=q, active=active, vector_status=vector_status, sort=sort, page=page_number, page_size=page_size, total=total, pages=pages, list_url=list_url, categories=COURSE_CATEGORIES)


@router.get("/courses/new")
async def new_course(request: Request, admin: User = Depends(get_admin)):
    return page(request, "admin/course_form.html", current_user=admin, course=None, errors=[], form_action="/admin/courses", next="/admin/courses", categories=COURSE_CATEGORIES)


@router.post("/courses")
async def create_course(request: Request, admin: User = Depends(get_admin), db: AsyncSession = Depends(get_db), title: str = Form(""), slug: str = Form(""), short_description: str = Form(""), description: str = Form(""), category: str = Form(""), tags: str = Form(""), price: Decimal = Form(0), currency: str = Form("USD"), difficulty: str = Form("BEGINNER"), instructor: str = Form(""), duration_minutes: int = Form(0), thumbnail_url: str = Form(""), is_featured: bool = Form(False), is_active: bool = Form(False), next: str = Form("/admin/courses"), csrf_token: str = Form("")):
    validate_csrf_token(request, csrf_token)
    values = _values(title, slug, short_description, description, category, tags, price, currency, difficulty, instructor, duration_minutes, thumbnail_url, is_featured, is_active)
    requested_slug = slugify(slug or title)
    if requested_slug and await db.scalar(select(Course.id).where(Course.slug == requested_slug)):
        return page(request, "admin/course_form.html", current_user=admin, course=FormBacking(**values), errors=["Slug already exists."], form_action="/admin/courses", categories=COURSE_CATEGORIES)
    form, errors = _form(**values)
    if errors:
        return page(request, "admin/course_form.html", current_user=admin, course=FormBacking(**values), errors=errors, form_action="/admin/courses", categories=COURSE_CATEGORIES)
    course_data = form.model_dump(exclude={"tags"})
    course_data["slug"] = form.slug or slugify(form.title)
    course = Course(**course_data, tags=form.tag_list(), vector_status="PENDING")
    db.add(course)
    await db.flush()
    db.add(_outbox(course, "UPSERT"))
    db.add(ActivityEvent(user_id=admin.id, session_id=server_session_id(request.session), event_type="ADMIN_COURSE_CREATED", course_id=course.id, metadata_json={}, occurred_at=datetime.now(timezone.utc).replace(tzinfo=None), received_at=datetime.now(timezone.utc).replace(tzinfo=None)))
    await db.commit()
    flash(request, "Course created and queued for vector sync.", "success")
    return RedirectResponse(safe_next(next), status_code=303)


@router.get("/courses/{course_id}/edit")
async def edit_course_page(course_id: str, request: Request, next: str = Query("/admin/courses"), admin: User = Depends(get_admin), db: AsyncSession = Depends(get_db)):
    course = await db.get(Course, course_id)
    if not course:
        raise HTTPException(404, "Course not found")
    return page(request, "admin/course_form.html", current_user=admin, course=course, errors=[], form_action=f"/admin/courses/{course_id}/edit", next=safe_next(next), categories=COURSE_CATEGORIES)


@router.post("/courses/{course_id}/edit")
async def edit_course(course_id: str, request: Request, admin: User = Depends(get_admin), db: AsyncSession = Depends(get_db), title: str = Form(""), slug: str = Form(""), short_description: str = Form(""), description: str = Form(""), category: str = Form(""), tags: str = Form(""), price: Decimal = Form(0), currency: str = Form("USD"), difficulty: str = Form("BEGINNER"), instructor: str = Form(""), duration_minutes: int = Form(0), thumbnail_url: str = Form(""), is_featured: bool = Form(False), is_active: bool = Form(False), next: str = Form("/admin/courses"), csrf_token: str = Form("")):
    validate_csrf_token(request, csrf_token)
    course = await db.get(Course, course_id)
    if not course:
        raise HTTPException(404, "Course not found")
    values = _values(title, slug, short_description, description, category, tags, price, currency, difficulty, instructor, duration_minutes, thumbnail_url, is_featured, is_active)
    form, errors = _form(**values)
    if errors:
        backing = FormBacking(id=course_id, **values)
        return page(request, "admin/course_form.html", current_user=admin, course=backing, errors=errors, form_action=f"/admin/courses/{course_id}/edit", categories=COURSE_CATEGORIES)
    data = form.model_dump(exclude={"tags"})
    data["tags"] = form.tag_list()
    data["slug"] = data["slug"] or slugify(data["title"])
    if await db.scalar(select(Course.id).where(Course.slug == data["slug"], Course.id != course.id)):
        backing = FormBacking(id=course_id, **values)
        return page(request, "admin/course_form.html", current_user=admin, course=backing, errors=["Slug already exists."], form_action=f"/admin/courses/{course_id}/edit", categories=COURSE_CATEGORIES)
    if apply_course_record(course, data):
        db.add(_outbox(course, "UPSERT" if course.is_active else "DELETE"))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(ActivityEvent(user_id=admin.id, session_id=server_session_id(request.session), event_type="ADMIN_COURSE_UPDATED", course_id=course.id, metadata_json={}, occurred_at=now, received_at=now))
    await db.commit()
    flash(request, "Course updated.", "success")
    return RedirectResponse(safe_next(next), status_code=303)


@router.post("/courses/{course_id}/restore")
async def restore_course(course_id: str, request: Request, csrf_token: str = Form(""), next: str = Form("/admin/courses"), admin: User = Depends(get_admin), db: AsyncSession = Depends(get_db)):
    validate_csrf_token(request, csrf_token)
    course = await db.get(Course, course_id)
    if not course:
        raise HTTPException(404, "Course not found")
    if not course.is_active:
        course.is_active = True
        course.version += 1
        course.vector_status = "PENDING"
        db.add(_outbox(course, "UPSERT"))
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db.add(ActivityEvent(user_id=admin.id, session_id=server_session_id(request.session), event_type="ADMIN_COURSE_UPDATED", course_id=course.id, metadata_json={"action": "restore"}, occurred_at=now, received_at=now))
        await db.commit()
        flash(request, "Course restored and queued for vector indexing.", "success")
    return RedirectResponse(safe_next(next), status_code=303)


@router.post("/courses/{course_id}/delete")
async def delete_course(course_id: str, request: Request, csrf_token: str = Form(""), next: str = Form("/admin/courses"), admin: User = Depends(get_admin), db: AsyncSession = Depends(get_db)):
    validate_csrf_token(request, csrf_token)
    course = await db.get(Course, course_id)
    if not course:
        raise HTTPException(404, "Course not found")
    if course.is_active:
        course.is_active = False
        course.version += 1
        course.vector_status = "DELETING"
        db.add(_outbox(course, "DELETE"))
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db.add(ActivityEvent(user_id=admin.id, session_id=server_session_id(request.session), event_type="ADMIN_COURSE_DELETED", course_id=course.id, metadata_json={}, occurred_at=now, received_at=now))
        await db.commit()
        flash(request, "Course archived and queued for vector removal.", "success")
    else:
        flash(request, "Course is already inactive.", "info")
    return RedirectResponse(safe_next(next), status_code=303)


@router.post("/vector-sync/{outbox_id}/retry")
async def retry_vector(outbox_id: str, request: Request, csrf_token: str = Form(""), admin: User = Depends(get_admin), db: AsyncSession = Depends(get_db)):
    validate_csrf_token(request, csrf_token)
    job = await db.get(VectorOutbox, outbox_id)
    if not job:
        raise HTTPException(404, "Vector job not found")
    if job.status == "FAILED":
        job.status, job.attempts, job.next_attempt_at = "PENDING", 0, datetime.now(timezone.utc).replace(tzinfo=None)
        await db.commit()
        flash(request, "Vector job queued for retry.", "success")
    return RedirectResponse("/admin/vector-sync", status_code=303)


@router.get("/vector-sync")
async def vector_sync(request: Request, admin: User = Depends(get_admin), db: AsyncSession = Depends(get_db)):
    jobs = list((await db.execute(select(VectorOutbox, Course.title).join(Course).order_by(VectorOutbox.updated_at.desc()).limit(100))).all())
    return page(request, "admin/vector_sync.html", current_user=admin, jobs=jobs)


@router.get("/recommendations")
async def recommendation_diagnostics(request: Request, admin: User = Depends(get_admin), db: AsyncSession = Depends(get_db), status: str = Query("", max_length=30), trigger_type: str = Query("", max_length=30), user: str = Query("", max_length=200), page_number: int = Query(1, alias="page", ge=1), page_size: int = Query(50, ge=1, le=100)):
    filters = []
    if status in {"PENDING", "RUNNING", "SUCCEEDED", "FALLBACK_SUCCEEDED", "FAILED", "SUPERSEDED"}:
        filters.append(RecommendationRun.status == status)
    if trigger_type:
        filters.append(RecommendationRun.trigger_type == trigger_type)
    if user:
        filters.append(User.email.ilike(f"%{' '.join(user.split())}%"))
    total = await db.scalar(select(func.count(RecommendationRun.id)).select_from(RecommendationRun).outerjoin(User).where(*filters)) or 0
    pages = max(1, (total + page_size - 1) // page_size)
    page_number = min(page_number, pages)
    rows = list((await db.execute(select(RecommendationRun, User.email).outerjoin(User).where(*filters).order_by(RecommendationRun.created_at.desc(), RecommendationRun.id.desc()).limit(page_size).offset((page_number - 1) * page_size))).all())
    return page(request, "admin/recommendations.html", current_user=admin, runs=rows, status=status, trigger_type=trigger_type, user=user, page=page_number, page_size=page_size, total=total, pages=pages)


@router.get("/recommendations/{run_id}")
async def recommendation_detail(run_id: str, request: Request, admin: User = Depends(get_admin), db: AsyncSession = Depends(get_db)):
    from sqlalchemy.orm import selectinload
    run = await db.scalar(select(RecommendationRun).options(selectinload(RecommendationRun.items).selectinload(RecommendationItem.course)).where(RecommendationRun.id == run_id))
    if not run:
        raise HTTPException(404, "Recommendation run not found")
    feedback_rows = list((await db.scalars(select(RecommendationFeedback).where(RecommendationFeedback.recommendation_run_id == run.id))).all())
    feedback_by_item = {item.recommendation_item_id: item for item in feedback_rows}
    return page(request, "admin/recommendation_detail.html", current_user=admin, run=run, feedback_by_item=feedback_by_item)


@router.get("/events")
async def events(request: Request, admin: User = Depends(get_admin), db: AsyncSession = Depends(get_db), event_type: str = Query("", max_length=40), user_id: str = Query("", max_length=36), user: str = Query("", max_length=200), course_id: str = Query("", max_length=36), date_from: str = Query("", max_length=30), date_to: str = Query("", max_length=30), session_prefix: str = Query("", max_length=20), page_number: int = Query(1, alias="page", ge=1), page_size: int = Query(50, ge=1, le=100)):
    from datetime import date
    filters = []
    if event_type in {"PAGE_VIEW", "COURSE_IMPRESSION", "COURSE_VIEW", "COURSE_CLICK", "SEARCH", "FILTER_CHANGE", "DWELL", "RECOMMENDATION_IMPRESSION", "RECOMMENDATION_CLICK", "RECOMMENDATION_DISMISS", "RECOMMENDATION_FEEDBACK_OPENED", "RECOMMENDATION_REJECTED", "RECOMMENDATION_REPLACEMENT_SHOWN", "ADMIN_COURSE_CREATED", "ADMIN_COURSE_UPDATED", "ADMIN_COURSE_DELETED"}:
        filters.append(ActivityEvent.event_type == event_type)
    if user_id:
        filters.append(ActivityEvent.user_id == user_id)
    if user:
        filters.append(User.email.ilike(f"%{' '.join(user.split())}%"))
    if course_id:
        filters.append(ActivityEvent.course_id == course_id)
    if session_prefix:
        filters.append(ActivityEvent.session_id.ilike(f"{session_prefix}%"))
    for value, operator in ((date_from, ">="), (date_to, "<")):
        if value:
            try:
                boundary = datetime.combine(date.fromisoformat(value), datetime.min.time())
                if operator == ">=": filters.append(ActivityEvent.occurred_at >= boundary)
                else: filters.append(ActivityEvent.occurred_at < boundary + timedelta(days=1))
            except ValueError:
                pass
    total = await db.scalar(select(func.count(ActivityEvent.id)).select_from(ActivityEvent).outerjoin(User).where(*filters)) or 0
    pages = max(1, (total + page_size - 1) // page_size)
    page_number = min(page_number, pages)
    rows = list((await db.execute(select(ActivityEvent, User.email, Course.title).outerjoin(User).outerjoin(Course).where(*filters).order_by(ActivityEvent.occurred_at.desc(), ActivityEvent.id.desc()).limit(page_size).offset((page_number - 1) * page_size))).all())
    return page(request, "admin/events.html", current_user=admin, events=rows, event_type=event_type, user_id=user_id, user=user, course_id=course_id, date_from=date_from, date_to=date_to, session_prefix=session_prefix, page=page_number, page_size=page_size, total=total, pages=pages)
