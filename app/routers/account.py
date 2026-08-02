from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_user
from app.models import User
from app.repositories.events import account_activity
from app.routers.helpers import page

router = APIRouter()


@router.get("/account")
async def account(request: Request, user: User = Depends(get_user), db: AsyncSession = Depends(get_db)):
    activity = await account_activity(db, user.id)
    return page(request, "account/index.html", current_user=user, activity=activity)
