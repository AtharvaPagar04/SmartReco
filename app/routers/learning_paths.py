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
from app.schemas.learning_path import DOMAIN_BY_CODE, DOMAIN_OPTIONS, FORMAT_PREFERENCES, GOALS, LEVELS, PATH_LENGTHS, PREFERENCES, PRIOR_SKILLS, QUICK_INSTRUCTIONS, LearningPathInput
from app.security import current_user
from app.services.cart_service import CartError, add_course_to_cart
from app.services.course_action_service import load_course_actions
from app.services.event_service import server_session_id
from app.services.form_error_service import friendly_validation_errors
from app.services.learning_path_service import create_learning_path, get_owned_path, replace_item
from app.services.learning_path_policy import MAX_FORMAT_PREFERENCES, MAX_LEARNING_GOALS, MAX_LEARNING_PREFERENCES, MAX_PRIOR_SKILLS, MAX_QUICK_INSTRUCTIONS, MAX_SELECTED_DOMAINS

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
    format_preferences = _form_list(form, "format_preferences") or _form_list(form, "format_preference")
    return {
        "primary_domain": primary_domain,
        "secondary_domains": secondary_domains,
        "goals": goals,
        "level": str(form.get("level", "")).strip(),
        "learning_preferences": _form_list(form, "learning_preferences"),
        "prior_skills": _form_list(form, "prior_skills"),
        "format_preferences": format_preferences,
        "weekly_hours": form.get("weekly_hours", ""),
        "target_weeks": form.get("target_weeks") or None,
        "budget_type": form.get("budget_type", "FLEXIBLE"),
        "budget_scope": form.get("budget_scope", "PATH"),
        "budget_amount": form.get("budget_amount") or None,
        "currency": form.get("currency", "USD"),
        "path_length": form.get("path_length", "AUTO"),
        "requested_course_count": form.get("requested_course_count") or 4,
        "optional_instruction": str(form.get("optional_instruction", ""))[:500],
        "quick_instructions": _form_list(form, "quick_instructions"),
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
        "Learning preferences": ", ".join(PREFERENCES.get(item, item) for item in draft.get("learning_preferences", [])) or "Not selected",
        "Prior skills": ", ".join(PRIOR_SKILLS.get(item, item) for item in draft.get("prior_skills", [])) or "None",
        "Format preferences": ", ".join(FORMAT_PREFERENCES.get(item, item) for item in draft.get("format_preferences", [draft.get("format_preference")] if draft.get("format_preference") else [])) or "None",
        "Path size": {"FOCUSED": "Focused path — 3–4 courses", "BALANCED": "Balanced path — 6–7 courses", "EXTENDED": "Deep path — target 8 courses", "DEEP": "Deep path — target 8 courses", "AUTO": "Let SmartReco decide — 3–8 courses"}.get(draft.get("path_length"), "Let SmartReco decide — 3–8 courses"),

    }
    return dict(current_user=user, domain_options=DOMAIN_OPTIONS, domain_groups=tuple(dict.fromkeys(item.group for item in DOMAIN_OPTIONS)), goals=GOALS, levels=LEVELS, preferences=PREFERENCES, prior_skills=PRIOR_SKILLS, formats=FORMAT_PREFERENCES, path_lengths=PATH_LENGTHS, quick_instructions=QUICK_INSTRUCTIONS, draft=draft, review_values=review_values, errors=errors or [], field_errors=field_errors or {}, active_step=active_step, selection_limits={"domains": MAX_SELECTED_DOMAINS, "goals": MAX_LEARNING_GOALS, "learning_preferences": MAX_LEARNING_PREFERENCES, "prior_skills": MAX_PRIOR_SKILLS, "format_preferences": MAX_FORMAT_PREFERENCES, "quick_instructions": MAX_QUICK_INSTRUCTIONS}, saved_paths=saved_paths or [])


async def _invalid_page(request: Request, db: AsyncSession, user: User | None, error: ValidationError):
    field_errors = friendly_validation_errors(error)
    step = next((2 if field in {"goals"} else 3 if field in {"level", "prior_skills"} else 4 if field in {"learning_preferences", "format_preferences"} else 5 if field in {"weekly_hours", "target_weeks", "requested_course_count"} else 6 if field in {"optional_instruction", "quick_instructions"} else 1 for field in field_errors), 1)
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
    saved_paths = list((await db.scalars(select(LearningPath).options(selectinload(LearningPath.items)).where(LearningPath.user_id == user.id, LearningPath.status != "ARCHIVED").order_by(LearningPath.created_at.desc()))).all()) if user else []
    return page(request, "path_builder/index.html", **_context(request, user, draft=draft, saved_paths=saved_paths))


@router.get("/path-builder/review")
async def path_builder_review(request: Request, db: AsyncSession = Depends(get_db)):
    user = await current_user(request, db)
    draft = request.session.get("path_builder_draft", {})
    saved_paths = list((await db.scalars(select(LearningPath).options(selectinload(LearningPath.items)).where(LearningPath.user_id == user.id, LearningPath.status != "ARCHIVED").order_by(LearningPath.created_at.desc()))).all()) if user else []
    return page(request, "path_builder/review.html", **_context(request, user, draft=draft, saved_paths=saved_paths))


@router.post("/path-builder/draft")
async def save_path_draft(request: Request, db: AsyncSession = Depends(get_db), csrf_token: str = Form("")):
    validate_csrf_token(request, csrf_token)
    user = await current_user(request, db)
    try:
        path_input = await _parse_input(request)
    except ValidationError as exc:
        return await _invalid_page(request, db, user, exc)
    payload = path_input.model_dump(mode="json")
    if not user:
        request.session["path_builder_draft"] = payload
        return RedirectResponse("/login?next=/path-builder", status_code=303)
    path = await create_learning_path(db, user, path_input, status="DRAFT")
    await db.commit()
    return RedirectResponse(f"/learning-paths/{path.id}", status_code=303)


@router.post("/path-builder/generate")
async def generate_path(request: Request, db: AsyncSession = Depends(get_db), csrf_token: str = Form("")):
    validate_csrf_token(request, csrf_token)
    user = await current_user(request, db)
    try:
        path_input = await _parse_input(request)
    except ValidationError as exc:
        return await _invalid_page(request, db, user, exc)
    if not user:
        request.session["path_builder_draft"] = path_input.model_dump(mode="json")
        return RedirectResponse("/login?next=/path-builder", status_code=303)
    path = await create_learning_path(db, user, path_input)
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
    await db.commit()
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
