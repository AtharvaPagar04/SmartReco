from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.csrf import validate_csrf_token, rotate_csrf_token
from app.config import settings
from app.database import get_db
from app.flash import flash
from app.models import ActivityEvent, RecommendationPreference, User
from app.routers.helpers import page
from app.repositories.users import by_email
from app.schemas.auth import LoginForm, RegistrationForm
from app.security import authenticate_session, hash_password, normalize_email, safe_next, verify_password
from app.services.event_service import server_session_id
from app.services.google_auth_service import GoogleAuthError, authorization_url, new_oauth_state, resolve_user, validate_oauth_state, verify_callback

router = APIRouter()


async def _record_google_event(db: AsyncSession, request: Request, event_type: str, user_id: str | None = None) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(ActivityEvent(user_id=user_id, session_id=server_session_id(request.session), event_type=event_type, page_path="/auth/google", metadata_json={"provider": "GOOGLE", "source": "auth", "outcome": "FAILURE" if event_type == "GOOGLE_AUTH_FAILED" else "SUCCESS"}, occurred_at=now, received_at=now))
    try:
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()


def _google_failure(request: Request, next_path: str, message: str) -> RedirectResponse:
    flash(request, message, "error")
    suffix = f"?next={quote(next_path, safe='/?=&')}" if next_path != "/" else ""
    return RedirectResponse(f"/login{suffix}", status_code=303)


@router.get("/register")
async def register_page(request: Request, next: str | None = None):
    return page(request, "auth/register.html", current_user=None, errors=[], next=safe_next(next), google_auth_enabled=settings.google_auth_enabled)


@router.post("/register")
async def register(request: Request, full_name: str = Form(""), email: str = Form(""), password: str = Form(""), password_confirm: str = Form(""), next: str = Form("/"), csrf_token: str = Form(""), db: AsyncSession = Depends(get_db)):
    validate_csrf_token(request, csrf_token)
    try:
        form = RegistrationForm(full_name=full_name, email=email, password=password, password_confirm=password_confirm)
        if not form.matching_passwords():
            raise ValueError("Passwords do not match")
    except ValueError as exc:
        return page(request, "auth/register.html", current_user=None, errors=[str(exc)], next=safe_next(next), google_auth_enabled=settings.google_auth_enabled)
    normalized = normalize_email(str(form.email))
    if await by_email(db, normalized):
        return page(request, "auth/register.html", current_user=None, errors=["An account with that email already exists."], next=safe_next(next), google_auth_enabled=settings.google_auth_enabled)
    user = User(full_name=form.full_name, email=normalized, password_hash=hash_password(form.password))
    db.add(user)
    await db.flush()
    db.add(RecommendationPreference(user_id=user.id, recommendations_enabled=True, session_followup_email_enabled=True))
    await db.commit()
    flash(request, "Account created. You can now log in.", "success")
    target = "/login" if safe_next(next) == "/" else f"/login?next={quote(safe_next(next), safe='/?=&')}"
    return RedirectResponse(target, status_code=303)


@router.get("/login")
async def login_page(request: Request, next: str | None = None):
    return page(request, "auth/login.html", current_user=None, errors=[], next=safe_next(next), google_auth_enabled=settings.google_auth_enabled)


@router.post("/login")
async def login(request: Request, email: str = Form(""), password: str = Form(""), next: str = Form("/"), csrf_token: str = Form(""), db: AsyncSession = Depends(get_db)):
    validate_csrf_token(request, csrf_token)
    try:
        form = LoginForm(email=email, password=password)
    except ValueError:
        return page(request, "auth/login.html", current_user=None, errors=["Enter a valid email and password."], next=safe_next(next), google_auth_enabled=settings.google_auth_enabled)
    user = await by_email(db, normalize_email(str(form.email)))
    if not user or not user.is_active or not verify_password(form.password, user.password_hash):
        return page(request, "auth/login.html", current_user=None, errors=["Email or password is incorrect."], next=safe_next(next), google_auth_enabled=settings.google_auth_enabled)
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    authenticate_session(request, user)
    rotate_csrf_token(request)
    target_next = safe_next(next)
    if target_next == "/" and user.role == "ADMIN":
        target_next = "/admin"
    return RedirectResponse(target_next, status_code=303)


@router.get("/auth/google")
async def google_start(request: Request, next: str | None = None, db: AsyncSession = Depends(get_db)):
    if not settings.google_auth_enabled:
        return _google_failure(request, "/", "Google sign-in is not available. You can still use your SmartReco email and password.")
    session_id = server_session_id(request.session)
    window_start = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=10)
    recent_attempts = await db.scalar(select(func.count(ActivityEvent.id)).where(ActivityEvent.session_id == session_id, ActivityEvent.event_type.in_(("GOOGLE_AUTH_STARTED", "GOOGLE_AUTH_FAILED")), ActivityEvent.occurred_at >= window_start)) or 0
    if recent_attempts >= 10:
        return _google_failure(request, "/", "Google sign-in could not be completed. Please try again later.")
    await _record_google_event(db, request, "GOOGLE_AUTH_STARTED")
    oauth = new_oauth_state(safe_next(next))
    request.session["google_oauth"] = oauth
    try:
        target = await authorization_url(oauth)
    except GoogleAuthError as exc:
        request.session.pop("google_oauth", None)
        return _google_failure(request, oauth["next_path"], exc.message)
    return RedirectResponse(target, status_code=302)


@router.get("/auth/google/callback")
async def google_callback(request: Request, db: AsyncSession = Depends(get_db)):
    oauth = request.session.pop("google_oauth", None)
    next_path = safe_next(oauth.get("next_path") if isinstance(oauth, dict) else None)
    if not settings.google_auth_enabled or not isinstance(oauth, dict):
        return _google_failure(request, next_path, "Google sign-in could not be completed. Please try again.")
    try:
        validate_oauth_state(oauth, request.query_params.get("state"))
        provider_error = request.query_params.get("error")
        if provider_error:
            message = "Google sign-in was cancelled." if provider_error == "access_denied" else "Google sign-in could not be completed. Please try again."
            await _record_google_event(db, request, "GOOGLE_AUTH_FAILED")
            return _google_failure(request, next_path, message)
        claims = await verify_callback(request.query_params.get("code", ""), oauth, request.query_params.get("state"))
        user, outcome = await resolve_user(db, claims)
        await db.commit()
        await _record_google_event(db, request, outcome, user.id)
        authenticate_session(request, user, authentication_method="GOOGLE")
        rotate_csrf_token(request)
        return RedirectResponse(next_path, status_code=303)
    except GoogleAuthError as exc:
        await db.rollback()
        await _record_google_event(db, request, "GOOGLE_AUTH_FAILED")
        return _google_failure(request, next_path, exc.message)


@router.post("/logout")
async def logout(request: Request, csrf_token: str = Form("")):
    validate_csrf_token(request, csrf_token)
    request.session.clear()
    flash(request, "You have been logged out.", "info")
    return RedirectResponse("/", status_code=303)
