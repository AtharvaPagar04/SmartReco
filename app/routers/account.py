from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.csrf import validate_csrf_token
from app.config import settings
from app.database import get_db
from app.dependencies import get_user
from app.models import ExternalIdentity, User
from app.repositories.events import account_activity
from app.repositories.enrollments import course_ids_for_user
from app.repositories.recommendations import current_for_user
from app.routers.helpers import page
from app.services.recommendation_view_service import build_recommendation_view
from app.services.course_action_service import load_course_actions, user_access_course_ids
from app.services.recommendation_context_service import build_learning_context

router = APIRouter()


@router.get("/account")
async def account(request: Request, user: User = Depends(get_user), db: AsyncSession = Depends(get_db)):
    activity = await account_activity(db, user.id)
    run = await current_for_user(db, user.id)
    excluded = await user_access_course_ids(db, user.id)
    actions = await load_course_actions(db, [item.course for item in run.items if item.course] if run else [], user.id)
    context = await build_learning_context(db, user.id)
    google_identity = await db.scalar(select(ExternalIdentity).where(ExternalIdentity.user_id == user.id, ExternalIdentity.provider == "GOOGLE"))
    return page(request, "account/index.html", current_user=user, activity=activity, learning_context=context, recommendation=build_recommendation_view(run, excluded, actions, context), google_auth_enabled=settings.google_auth_enabled, google_identity=google_identity)



@router.post("/account/profile")
async def update_profile(
    request: Request,
    user: User = Depends(get_user),
    db: AsyncSession = Depends(get_db),
    csrf_token: str = Form(""),
    full_name: str = Form(...),
    headline: str | None = Form(None),
    bio: str | None = Form(None),
    location: str | None = Form(None),
    primary_domain: str | None = Form(None),
):
    validate_csrf_token(request, csrf_token)
    user_db = await db.get(User, user.id)
    if user_db:
        user_db.full_name = full_name.strip()
        user_db.headline = headline.strip() if headline else None
        user_db.bio = bio.strip() if bio else None
        user_db.location = location.strip() if location else None
        user_db.primary_domain = primary_domain.strip() if primary_domain else None
        await db.commit()
    return RedirectResponse("/account", status_code=303)
