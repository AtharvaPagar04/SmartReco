import logging

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.routers.helpers import templates

logger = logging.getLogger(__name__)


def is_api(request: Request) -> bool:
    return request.url.path.startswith("/api/") or "application/json" in request.headers.get("accept", "")


def error_response(request: Request, status: int, code: str, message: str):
    if is_api(request):
        return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})
    template = {403: "errors/403.html", 404: "errors/404.html"}.get(status, "errors/500.html")
    return templates.TemplateResponse(request=request, name=template, context={"request": request, "csrf_token": request.session.get("csrf_token", ""), "flashes": []}, status_code=status)


async def http_exception_handler(request: Request, exc: HTTPException):
    messages = {401: "Please log in to continue.", 403: "You do not have permission to do that.", 404: "The requested page was not found."}
    return error_response(request, exc.status_code, "http_error", messages.get(exc.status_code, str(exc.detail)))


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return error_response(request, 422, "validation_error", "The submitted data is invalid.")


async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled application error", extra={"path": request.url.path})
    return error_response(request, 500, "internal_error", "Something went wrong. Please try again.")
