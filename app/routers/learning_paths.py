from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.csrf import validate_csrf_token
from app.database import get_db
from app.dependencies import get_user
from app.flash import flash
from app.models import ActivityEvent, LearningPath, User
from app.routers.helpers import page
from app.schemas.learning_path import DOMAIN_BY_CODE, DOMAIN_OPTIONS, GOALS, LEVELS, PATH_LENGTHS, LearningPathInput
from app.security import current_user
from app.services.cart_service import CartError, add_course_to_cart
from app.services.course_action_service import load_course_actions
from app.services.event_service import server_session_id
from app.services.form_error_service import friendly_validation_errors
from app.services.learning_path_service import create_learning_path, get_owned_path, replace_item
from app.services.learning_path_policy import MAX_LEARNING_GOALS, MAX_SELECTED_DOMAINS

router = APIRouter()
def _form_list(form, name: str) -> list[str]:
    return [str(value).strip() for value in form.getlist(name) if str(value).strip()]


def _raw_form(form) -> dict:
    selected_domains = _form_list(form, "selected_domains")
    ordered_domains = [item for item in str(form.get("selected_domains_order", "")).split(",") if item]
    if ordered_domains and len(ordered_domains) == len(selected_domains) and set(ordered_domains) == set(selected_domains):
        selected_domains = ordered_domains
    if selected_domains:
        primary_domain, secondary_domains = selected_domains[0], selected_domains[1:]
    else:
        primary_domain = str(form.get("primary_domain", "")).strip()
        secondary_domains = _form_list(form, "secondary_domains")
    goals = _form_list(form, "goals") or _form_list(form, "goal")
    return {
        "primary_domain": primary_domain,
        "secondary_domains": secondary_domains,
        "goals": goals,
        "level": str(form.get("level", "")).strip(),
        "weekly_hours": form.get("weekly_hours", ""),
        "target_weeks": form.get("target_weeks") or None,
        "budget_type": form.get("budget_type", "FLEXIBLE"),
        "budget_scope": form.get("budget_scope", "PATH"),
        "budget_amount": form.get("budget_amount") or None,
        "currency": form.get("currency", "USD"),
        "path_length": form.get("path_length", "AUTO"),
        "requested_course_count": form.get("requested_course_count") or 4,
    }


async def _parse_input(request: Request) -> LearningPathInput:
    return LearningPathInput.model_validate(_raw_form(await request.form()))


def _context(request: Request, user: User | None, *, draft: dict | None = None, errors: list[str] | None = None, field_errors: dict[str, str] | None = None, active_step: int = 1, saved_paths: list | None = None):
    draft = dict(draft or {})
    draft.setdefault("selected_domains", [value for value in [draft.get("primary_domain"), *(draft.get("secondary_domains") or [])] if value])
    review_values = {
        "Primary domain": DOMAIN_BY_CODE.get(draft.get("primary_domain"), None).label if draft.get("primary_domain") in DOMAIN_BY_CODE else "Not selected",
        "Secondary interests": ", ".join(DOMAIN_BY_CODE[item].label for item in draft.get("secondary_domains", []) if item in DOMAIN_BY_CODE) or "None",
        "Learning goals": ", ".join(GOALS.get(item, item) for item in draft.get("goals", [draft.get("goal")] if draft.get("goal") else [])) or "Not selected",
        "Current level": LEVELS.get(draft.get("level"), "Not selected"),
        "Weekly time": f"{draft.get('weekly_hours', 0)} hours/week" if draft.get("weekly_hours") else "Not selected",
        "Desired horizon": {None: "Flexible", "": "Flexible", 1: "1 week", 4: "1 month", 8: "2 months", 12: "3 months"}.get(draft.get("target_weeks"), "Flexible"),
        "Path size": {"FOCUSED": "Focused path — 3–4 courses", "BALANCED": "Balanced path — 6–7 courses", "EXTENDED": "Deep path — target 8 courses", "DEEP": "Deep path — target 8 courses", "AUTO": "Let SmartReco decide — 3–8 courses"}.get(draft.get("path_length"), "Let SmartReco decide — 3–8 courses"),

    }
    return dict(current_user=user, domain_options=DOMAIN_OPTIONS, domain_groups=tuple(dict.fromkeys(item.group for item in DOMAIN_OPTIONS)), goals=GOALS, levels=LEVELS, path_lengths=PATH_LENGTHS, draft=draft, review_values=review_values, errors=errors or [], field_errors=field_errors or {}, active_step=active_step, selection_limits={"domains": MAX_SELECTED_DOMAINS, "goals": MAX_LEARNING_GOALS}, saved_paths=saved_paths or [])


async def _invalid_page(request: Request, db: AsyncSession, user: User | None, error: ValidationError):
    field_errors = friendly_validation_errors(error)
    step = next((2 if field == "goals" else 3 if field == "level" else 4 if field in {"weekly_hours", "target_weeks", "requested_course_count", "budget_amount"} else 1 for field in field_errors), 1)
    saved_paths = list((await db.scalars(select(LearningPath).options(selectinload(LearningPath.items)).where(LearningPath.user_id == user.id, LearningPath.status != "ARCHIVED").order_by(LearningPath.created_at.desc()))).all()) if user else []
    return page(request, "path_builder/index.html", **_context(request, user, draft=_raw_form(await request.form()), errors=list(dict.fromkeys(field_errors.values())), field_errors=field_errors, active_step=step, saved_paths=saved_paths))


async def _record_path_event(
    db: AsyncSession,
    request: Request,
    user_id: str,
    event_type: str,
    *,
    path_id: str,
    primary_domain: str,
    goal_code: str,
    course_count: int,
) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(
        ActivityEvent(
            user_id=user_id,
            session_id=server_session_id(request.session),
            event_type=event_type,
            page_path="/path-builder",
            metadata_json={
                "path_id": path_id,
                "domain_code": primary_domain,
                "goal_code": goal_code,
                "course_count": course_count,
            },
            occurred_at=now,
            received_at=now,
        )
    )


@router.get("/path-builder")
async def path_builder(request: Request, db: AsyncSession = Depends(get_db)):
    user = await current_user(request, db)
    draft = request.session.get("path_builder_draft", {})
    edit_path_id = request.query_params.get("edit_path_id")
    if user and edit_path_id:
        path = await get_owned_path(db, user.id, edit_path_id)
        if path:
            draft = LearningPathInput.model_validate(path.input_json).model_dump(mode="json")
            request.session["path_builder_draft"] = draft
    saved_paths = list((await db.scalars(select(LearningPath).options(selectinload(LearningPath.items)).where(LearningPath.user_id == user.id, LearningPath.status != "ARCHIVED").order_by(LearningPath.created_at.desc()))).all()) if user else []
    return page(request, "path_builder/index.html", **_context(request, user, draft=draft, saved_paths=saved_paths))


@router.get("/path-builder/review")
async def path_builder_review(request: Request, db: AsyncSession = Depends(get_db)):
    user = await current_user(request, db)
    draft = request.session.get("path_builder_draft", {})
    saved_paths = list((await db.scalars(select(LearningPath).options(selectinload(LearningPath.items)).where(LearningPath.user_id == user.id, LearningPath.status != "ARCHIVED").order_by(LearningPath.created_at.desc()))).all()) if user else []
    return page(request, "path_builder/review.html", **_context(request, user, draft=draft, saved_paths=saved_paths))



import time
import uuid
import logging
from app.services.learning_path_logging import LearningPathTraceContext, log_learning_path_step

router_logger = logging.getLogger("app.routers.learning_paths")


@router.post("/path-builder/generate")
async def generate_path(request: Request, db: AsyncSession = Depends(get_db), csrf_token: str = Form("")):
    validate_csrf_token(request, csrf_token)
    user = await current_user(request, db)

    trace_id = getattr(request.state, "trace_id", None) or getattr(request.state, "request_id", None) or str(uuid.uuid4())
    trace_context = LearningPathTraceContext(trace_id=trace_id)

    raw = _raw_form(await request.form())
    user_id_str = user.id if user else "anonymous"

    log_learning_path_step(
        router_logger,
        "learning_path.request.start",
        trace_id,
        user_id=user_id_str,
        path_mode=raw.get("path_length"),
        primary_domain=raw.get("primary_domain"),
        secondary_domain_count=len(raw.get("secondary_domains", [])),
        goal_count=len(raw.get("goals", [])),
        level=raw.get("level"),
        weekly_hours=raw.get("weekly_hours"),
    )

    log_learning_path_step(
        router_logger,
        "learning_path.step.start",
        trace_id,
        step="form.parse",
    )
    t_fp = time.perf_counter()
    try:
        path_input = LearningPathInput.model_validate(raw)
        fp_dur = (time.perf_counter() - t_fp) * 1000
        log_learning_path_step(
            router_logger,
            "learning_path.step.success",
            trace_id,
            step="form.parse",
            duration_ms=fp_dur,
            selected_domain_count=len(raw.get("secondary_domains", [])) + 1,
            goal_count=len(raw.get("goals", [])),
            path_mode=raw.get("path_length"),
        )
    except ValidationError as exc:
        fp_dur = (time.perf_counter() - t_fp) * 1000
        field_errs = friendly_validation_errors(exc)
        val_fields = list(field_errs.keys())

        log_learning_path_step(
            router_logger,
            "learning_path.step.error",
            trace_id,
            step="form.parse",
            duration_ms=fp_dur,
            exception_type="ValidationError",
            validation_field_names=val_fields,
        )
        trace_context.record_failure("form.parse", "VALIDATION_ERROR")
        log_learning_path_step(
            router_logger,
            "learning_path.request.failed",
            trace_id,
            path_id=None,
            final_status="FAILED",
            first_failure_stage=trace_context.first_failure_stage,
            first_failure_reason=trace_context.first_failure_reason,
            final_failure_stage=trace_context.final_failure_stage,
            final_failure_reason=trace_context.final_failure_reason,
            total_duration_ms=trace_context.elapsed_ms(),
        )
        return await _invalid_page(request, db, user, exc)

    if not user:
        request.session["path_builder_draft"] = path_input.model_dump(mode="json")
        return RedirectResponse("/login?next=/path-builder", status_code=303)

    path = await create_learning_path(db, user, path_input, trace_context=trace_context)
    request.session.pop("path_builder_draft", None)
    loaded = await get_owned_path(db, user.id, path.id)
    course_count = len(loaded.items) if loaded else 0

    await _record_path_event(
        db,
        request,
        user.id,
        "LEARNING_PATH_GENERATED",
        path_id=path.id,
        primary_domain=path.primary_domain,
        goal_code=path.goal_code,
        course_count=course_count,
    )
    await _record_path_event(
        db,
        request,
        user.id,
        "LEARNING_PATH_SAVED",
        path_id=path.id,
        primary_domain=path.primary_domain,
        goal_code=path.goal_code,
        course_count=course_count,
    )

    t_com = time.perf_counter()
    log_learning_path_step(
        router_logger,
        "learning_path.step.start",
        trace_id,
        step="persistence.commit",
    )
    try:
        await db.commit()
        com_dur = (time.perf_counter() - t_com) * 1000
        log_learning_path_step(
            router_logger,
            "learning_path.step.success",
            trace_id,
            step="persistence.commit",
            duration_ms=com_dur,
        )
    except Exception as exc:
        com_dur = (time.perf_counter() - t_com) * 1000
        await db.rollback()
        log_learning_path_step(
            router_logger,
            "learning_path.step.error",
            trace_id,
            step="persistence.rollback",
            duration_ms=com_dur,
            exception_class=exc.__class__.__name__,
        )
        trace_context.record_failure("persistence.commit", "COMMIT_FAILED")
        log_learning_path_step(
            router_logger,
            "learning_path.request.failed",
            trace_id,
            path_id=path.id,
            final_status="FAILED",
            first_failure_stage=trace_context.first_failure_stage,
            first_failure_reason=trace_context.first_failure_reason,
            final_failure_stage=trace_context.final_failure_stage,
            final_failure_reason=trace_context.final_failure_reason,
            total_duration_ms=trace_context.elapsed_ms(),
        )
        raise exc

    if path.status in ("FAILED", "INSUFFICIENT_COVERAGE"):
        log_learning_path_step(
            router_logger,
            "learning_path.request.failed",
            trace_id,
            path_id=path.id,
            final_status=str(path.status.value if hasattr(path.status, 'value') else path.status),
            first_failure_stage=trace_context.first_failure_stage,
            first_failure_reason=trace_context.first_failure_reason,
            final_failure_stage=trace_context.final_failure_stage,
            final_failure_reason=trace_context.final_failure_reason,
            total_duration_ms=trace_context.elapsed_ms(),
        )
    else:
        source_str = "MESH" if path.used_mesh else "FALLBACK"
        log_learning_path_step(
            router_logger,
            "learning_path.request.success",
            trace_id,
            path_id=path.id,
            status=str(path.status.value if hasattr(path.status, 'value') else path.status),
            selected_count=course_count,
            source=source_str,
            total_duration_ms=trace_context.elapsed_ms(),
        )

    return RedirectResponse(f"/learning-paths/{path.id}", status_code=303)


@router.get("/learning-paths")
async def learning_paths(request: Request, user: User = Depends(get_user), db: AsyncSession = Depends(get_db)):
    return RedirectResponse("/path-builder", status_code=303)


@router.get("/learning-paths/{path_id}")
async def learning_path_detail(path_id: str, request: Request, user: User = Depends(get_user), db: AsyncSession = Depends(get_db)):
    path = await get_owned_path(db, user.id, path_id)
    if not path:
        raise HTTPException(status_code=404, detail="Learning path not found")
    courses = [item.course for item in path.items if item.course]
    actions = await load_course_actions(db, courses, user.id)
    completed = sum(1 for course in courses if actions[course.id].state == "COMPLETED")
    return page(request, "learning_paths/detail.html", current_user=user, path=path, actions=actions, completed_count=completed)


@router.post("/learning-paths/{path_id}/regenerate")
async def regenerate_path(path_id: str, request: Request, user: User = Depends(get_user), db: AsyncSession = Depends(get_db), csrf_token: str = Form("")):
    validate_csrf_token(request, csrf_token)
    old = await get_owned_path(db, user.id, path_id)
    if not old:
        raise HTTPException(status_code=404, detail="Learning path not found")
    old.status = "ARCHIVED"
    path = await create_learning_path(db, user, LearningPathInput.model_validate(old.input_json))
    loaded = await get_owned_path(db, user.id, path.id)
    course_count = len(loaded.items) if loaded else 0
    await _record_path_event(
        db,
        request,
        user.id,
        "LEARNING_PATH_GENERATED",
        path_id=path.id,
        primary_domain=path.primary_domain,
        goal_code=path.goal_code,
        course_count=course_count,
    )
    await db.commit()
    return RedirectResponse(f"/learning-paths/{path.id}", status_code=303)


@router.post("/learning-paths/{path_id}/archive")
async def archive_path(path_id: str, request: Request, user: User = Depends(get_user), db: AsyncSession = Depends(get_db), csrf_token: str = Form("")):
    validate_csrf_token(request, csrf_token)
    path = await get_owned_path(db, user.id, path_id)
    if not path:
        raise HTTPException(status_code=404, detail="Learning path not found")
    path.status = "ARCHIVED"
    path.archived_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await _record_path_event(
        db,
        request,
        user.id,
        "LEARNING_PATH_ARCHIVED",
        path_id=path.id,
        primary_domain=path.primary_domain,
        goal_code=path.goal_code,
        course_count=len(path.items),
    )
    await db.commit()
    return RedirectResponse("/path-builder", status_code=303)


@router.post("/learning-paths/{path_id}/items/{item_id}/replace")
async def replace_path_item(path_id: str, item_id: str, request: Request, reason: str = Form("PREFER_TOPIC"), user: User = Depends(get_user), db: AsyncSession = Depends(get_db), csrf_token: str = Form("")):
    validate_csrf_token(request, csrf_token)
    path = await get_owned_path(db, user.id, path_id)
    if not path:
        raise HTTPException(status_code=404, detail="Learning path not found")
    item = next((value for value in path.items if value.id == item_id), None)
    if not item or not item.course:
        raise HTTPException(status_code=404, detail="Path stage not found")
    if not await replace_item(db, path, item, reason):
        flash(request, "No grounded replacement is available right now.", "warning")
    else:
        await _record_path_event(
            db,
            request,
            user.id,
            "LEARNING_PATH_COURSE_REPLACED",
            path_id=path.id,
            primary_domain=path.primary_domain,
            goal_code=path.goal_code,
            course_count=len(path.items),
        )
        flash(request, "The stage was replaced and the totals were recalculated.", "success")
    await db.commit()
    return RedirectResponse(f"/learning-paths/{path.id}", status_code=303)


@router.post("/learning-paths/{path_id}/add-paid-courses-to-cart")
async def add_path_courses_to_cart(path_id: str, request: Request, user: User = Depends(get_user), db: AsyncSession = Depends(get_db), csrf_token: str = Form("")):
    validate_csrf_token(request, csrf_token)
    path = await get_owned_path(db, user.id, path_id)
    if not path:
        raise HTTPException(status_code=404, detail="Learning path not found")
    added, skipped = 0, 0
    for item in path.items:
        if not item.course or item.course.price <= 0:
            skipped += 1
            continue
        try:
            result = await add_course_to_cart(db, user_id=user.id, course_slug=item.course.slug)
            added += int(result.added)
            skipped += int(not result.added)
        except CartError:
            skipped += 1
    await db.commit()
    flash(request, f"Added {added} paid course(s) to your cart; skipped {skipped}.", "success" if added else "info")
    return RedirectResponse(f"/learning-paths/{path.id}", status_code=303)
