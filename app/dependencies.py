from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.security import current_user


async def get_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    user = await current_user(request, db)
    if not user:
        raise HTTPException(status_code=403, detail="Login required")
    return user


async def get_admin(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    user = await current_user(request, db)
    if not user or user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user
