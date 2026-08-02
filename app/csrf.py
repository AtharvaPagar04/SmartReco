import hmac
import secrets

from fastapi import HTTPException, Request


def ensure_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def rotate_csrf_token(request: Request) -> str:
    token = secrets.token_urlsafe(32)
    request.session["csrf_token"] = token
    return token


def validate_csrf_token(request: Request, submitted_token: str | None) -> None:
    expected = request.session.get("csrf_token", "")
    if not submitted_token or not expected or not hmac.compare_digest(expected, submitted_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


def validate_json_csrf(request: Request) -> None:
    validate_csrf_token(request, request.headers.get("X-CSRF-Token"))


def validate_beacon_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    host = request.headers.get("host", "")
    if origin and origin.split("//", 1)[-1].rstrip("/") != host:
        raise HTTPException(status_code=403, detail="Cross-origin beacon rejected")
    if not origin and referer and referer.split("//", 1)[-1].split("/", 1)[0] != host:
        raise HTTPException(status_code=403, detail="Cross-origin beacon rejected")
