from datetime import datetime, timezone
from urllib.parse import urlsplit

from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.models import User

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def safe_next(value: str | None) -> str:
    if not value:
        return "/"
    parsed = urlsplit(value)
    return value if not parsed.scheme and not parsed.netloc and value.startswith("/") else "/"


async def current_user(request: Request, db: AsyncSession) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = await db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if not user:
        request.session.clear()
    return user


def authenticate_session(request: Request, user: User) -> None:
    csrf = request.session.get("csrf_token")
    session_id = request.session.get("session_id")
    request.session.clear()
    request.session.update({"user_id": user.id, "session_id": session_id, "auth_at": datetime.now(timezone.utc).isoformat()})
    if csrf:
        request.session["csrf_token"] = csrf


def logout_session(request: Request) -> None:
    request.session.clear()
