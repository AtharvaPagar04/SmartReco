from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import engine, run_migrations
from app.exception_handlers import http_exception_handler, unhandled_exception_handler, validation_exception_handler
from app.jobs.scheduler import build_scheduler
from app.logging_config import configure_logging, request_id_middleware
from app.routers import account, admin, auth, catalog, commerce, events, health, learning_paths, recommendations, search

from app.services.schema_readiness_service import check_schema_readiness


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_runtime()
    await run_migrations()
    await check_schema_readiness(engine)
    scheduler = build_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    yield
    scheduler.shutdown(wait=False)


configure_logging(settings.log_level)
app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, session_cookie=settings.session_cookie_name, max_age=settings.session_max_age_seconds, https_only=settings.session_https_only, same_site="lax")
app.middleware("http")(request_id_middleware)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(health.router)
app.include_router(catalog.router)

app.include_router(commerce.router)
app.include_router(auth.router)
app.include_router(account.router)
app.include_router(events.router)
app.include_router(search.router)
app.include_router(recommendations.router)
app.include_router(learning_paths.router)
app.include_router(admin.router)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)
