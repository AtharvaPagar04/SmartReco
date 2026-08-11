from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.csrf import validate_csrf_token, validate_json_csrf
from app.database import get_db
from app.dependencies import get_user
from app.models import ActivityEvent, RecommendationFeedback, RecommendationItem, RecommendationPreference, RecommendationState, User
from app.repositories.recommendation_feedback import FEEDBACK_REASONS, record_feedback
from app.repositories.recommendations import current_for_user, get_or_create_recommendation_preference
from app.repositories.enrollments import course_ids_for_user
from app.routers.helpers import page
from app.services.event_service import server_session_id
from app.services.recommendation_policy_service import mark_user_dirty

from app.services.recommendation_view_service import build_recommendation_view
from app.services.course_action_service import load_course_actions, user_access_course_ids
from app.services.recommendation_context_service import build_learning_context
from app.services.recommendation_replacement_service import create_feedback_replacement

router = APIRouter()


async def _pending_replacement(db: AsyncSession, user_id: str, run) -> dict | None:
    if not run:
        return None
    latest = await db.scalar(select(RecommendationFeedback).where(RecommendationFeedback.user_id == user_id).order_by(RecommendationFeedback.created_at.desc()).limit(1))
    if not latest or latest.recommendation_run_id != run.id or not latest.created_at or not run.created_at or latest.created_at <= run.created_at:
        return None
    item = await db.get(RecommendationItem, latest.recommendation_item_id)
    return {"rank": item.rank, "rejected_item_id": item.id} if item and item.dismissed_at else None


async def _ensure_view_backfill(db: AsyncSession, user_id: str, run, excluded: set[str]) -> None:
    if not run:
        return
    for item in run.items:
        if (item.course_id in excluded or item.dismissed_at is not None) and item.course:
            await create_feedback_replacement(db, user_id, item.id)
            break


@router.get("/api/recommendations/current")
async def current(request: Request, response: Response, user: User = Depends(get_user), db: AsyncSession = Depends(get_db)):
    run = await current_for_user(db, user.id)
    response.headers["Cache-Control"] = "private, no-store"
    excluded = await user_access_course_ids(db, user.id)
    if run:
        await _ensure_view_backfill(db, user.id, run, excluded)
        run = await current_for_user(db, user.id)
    actions = await load_course_actions(db, [item.course for item in run.items if item.course] if run else [], user.id)
    context = await build_learning_context(db, user.id)
    return {"recommendation": build_recommendation_view(run, excluded, actions, context, await _pending_replacement(db, user.id, run))}


async def _run_recommendation_background(user_id: str) -> None:
    from app.database import async_session_maker
    from app.services.recommendation_service import generate_recommendation
    async with async_session_maker() as session:
        try:
            await generate_recommendation(session, user_id, trigger_type="MANUAL_REQUEST", force=True)
        except Exception:
            await session.rollback()


@router.post("/api/recommendations/refresh", status_code=202)
async def refresh(request: Request, user: User = Depends(get_user), db: AsyncSession = Depends(get_db)):
    validate_json_csrf(request)
    await mark_user_dirty(db, user.id, immediate=True)
    await db.commit()
    import asyncio
    asyncio.create_task(_run_recommendation_background(user.id))
    return {"status": "accepted", "message": "Recommendation refresh queued."}


async def _feedback_submission(item_id: str, request: Request, user: User, db: AsyncSession, *, default_reason: str | None = None, event_type: str = "RECOMMENDATION_REJECTED", legacy: bool = False):
    is_json = request.headers.get("content-type", "").split(";", 1)[0].lower() == "application/json"
    if is_json:
        validate_json_csrf(request)
        body = await request.json()
        reason_code = str(body.get("reason_code") or default_reason or "")
        comment = body.get("optional_comment")
    else:
        form = await request.form()
        validate_csrf_token(request, str(form.get("csrf_token", "")))
        reason_code = str(form.get("reason_code") or default_reason or "")
        comment = form.get("optional_comment")
    try:
        feedback = await record_feedback(db, user_id=user.id, recommendation_item_id=item_id, reason_code=reason_code, optional_comment=comment)
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(404 if detail == "recommendation_item_not_found" else 400, detail) from exc
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(ActivityEvent(user_id=user.id, session_id=server_session_id(request.session), event_type=event_type, course_id=feedback.course_id, metadata_json={"source": "recommendation", "recommendation_run_id": feedback.recommendation_run_id, "recommendation_item_id": feedback.recommendation_item_id, "reason_code": feedback.reason_code}, occurred_at=now, received_at=now))
    await mark_user_dirty(db, user.id, occurred_at=now, immediate=True)
    await db.commit()
    replacement = await create_feedback_replacement(db, user.id, item_id)
    payload = {"status": "accepted", "dismissed_item_id": item_id, "replacement_pending": replacement is None, "recommendation_run_id": replacement.id if replacement else None}
    if legacy:
        payload.update(status="dismissed", item_id=item_id)
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse(payload, status_code=200 if legacy else 202)
    return RedirectResponse("/recommendations", status_code=303)


@router.post("/api/recommendations/items/{item_id}/feedback")
async def feedback(item_id: str, request: Request, user: User = Depends(get_user), db: AsyncSession = Depends(get_db)):
    return await _feedback_submission(item_id, request, user, db)


@router.post("/api/recommendations/items/{item_id}/dismiss")
async def dismiss(item_id: str, request: Request, user: User = Depends(get_user), db: AsyncSession = Depends(get_db)):
    return await _feedback_submission(item_id, request, user, db, default_reason="NOT_RELEVANT_NOW", event_type="RECOMMENDATION_DISMISS", legacy=True)


@router.get("/recommendations")
async def page_view(request: Request, user: User = Depends(get_user), db: AsyncSession = Depends(get_db)):
    run = await current_for_user(db, user.id)
    excluded = await user_access_course_ids(db, user.id)
    if run:
        await _ensure_view_backfill(db, user.id, run, excluded)
        run = await current_for_user(db, user.id)
    actions = await load_course_actions(db, [item.course for item in run.items if item.course] if run else [], user.id)
    context = await build_learning_context(db, user.id)
    return page(request, "account/recommendations.html", current_user=user, recommendation=build_recommendation_view(run, excluded, actions, context, await _pending_replacement(db, user.id, run)), feedback_reasons=FEEDBACK_REASONS)



@router.post("/account/recommendation-preferences")
async def update_preferences(
    request: Request,
    user: User = Depends(get_user),
    db: AsyncSession = Depends(get_db),
    csrf_token: str = Form(""),
    recommendations_enabled: bool = Form(False),
    session_followup_email_enabled: bool = Form(False),
    email_digest_enabled: bool = Form(False),
):
    validate_csrf_token(request, csrf_token)
    preference = await get_or_create_recommendation_preference(db, user.id)
    preference.recommendations_enabled = recommendations_enabled
    preference.session_followup_email_enabled = session_followup_email_enabled
    preference.email_digest_enabled = email_digest_enabled
    await db.commit()
    referer = request.headers.get("referer", "/account")
    target = "/account" if "/account" in referer else ("/recommendations" if "/recommendations" in referer else "/account")
    return RedirectResponse(target, status_code=303)
