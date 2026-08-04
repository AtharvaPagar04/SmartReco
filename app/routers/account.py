from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_user
from app.models import User
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
    return page(request, "account/index.html", current_user=user, activity=activity, recommendation=build_recommendation_view(run, excluded, actions, context))
