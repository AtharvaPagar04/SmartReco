from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.csrf import validate_csrf_token, rotate_csrf_token
from app.database import get_db
from app.flash import flash
from app.models import User
from app.routers.helpers import page
from app.repositories.users import by_email
from app.schemas.auth import LoginForm, RegistrationForm
from app.security import authenticate_session, hash_password, normalize_email, safe_next, verify_password

router = APIRouter()


@router.get("/register")
async def register_page(request: Request):
    return page(request, "auth/register.html", current_user=None, errors=[])


@router.post("/register")
async def register(request: Request, full_name: str = Form(""), email: str = Form(""), password: str = Form(""), password_confirm: str = Form(""), csrf_token: str = Form(""), db: AsyncSession = Depends(get_db)):
    validate_csrf_token(request, csrf_token)
    try:
        form = RegistrationForm(full_name=full_name, email=email, password=password, password_confirm=password_confirm)
        if not form.matching_passwords():
            raise ValueError("Passwords do not match")
    except ValueError as exc:
        return page(request, "auth/register.html", current_user=None, errors=[str(exc)])
    normalized = normalize_email(str(form.email))
    if await by_email(db, normalized):
        return page(request, "auth/register.html", current_user=None, errors=["An account with that email already exists."])
    db.add(User(full_name=form.full_name, email=normalized, password_hash=hash_password(form.password)))
    await db.commit()
    flash(request, "Account created. You can now log in.", "success")
    return RedirectResponse("/login", status_code=303)


@router.get("/login")
async def login_page(request: Request, next: str | None = None):
    return page(request, "auth/login.html", current_user=None, errors=[], next=safe_next(next))


@router.post("/login")
async def login(request: Request, email: str = Form(""), password: str = Form(""), next: str = Form("/"), csrf_token: str = Form(""), db: AsyncSession = Depends(get_db)):
    validate_csrf_token(request, csrf_token)
    try:
        form = LoginForm(email=email, password=password)
    except ValueError:
        return page(request, "auth/login.html", current_user=None, errors=["Enter a valid email and password."], next=safe_next(next))
    user = await by_email(db, normalize_email(str(form.email)))
    if not user or not user.is_active or not verify_password(form.password, user.password_hash):
        return page(request, "auth/login.html", current_user=None, errors=["Email or password is incorrect."], next=safe_next(next))
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    authenticate_session(request, user)
    rotate_csrf_token(request)
    target_next = safe_next(next)
    if target_next == "/" and user.role == "ADMIN":
        target_next = "/admin"
    return RedirectResponse(target_next, status_code=303)


@router.post("/logout")
async def logout(request: Request, csrf_token: str = Form("")):
    validate_csrf_token(request, csrf_token)
    request.session.clear()
    flash(request, "You have been logged out.", "info")
    return RedirectResponse("/", status_code=303)
