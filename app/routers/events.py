import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.csrf import validate_beacon_origin, validate_json_csrf
from app.database import get_db
from app.security import current_user
from app.schemas.event import EventInput
from app.services.event_service import ingest_events, server_session_id

router = APIRouter(prefix="/api/events")


async def _ingest(request: Request, db: AsyncSession, *, beacon: bool = False):
    if not request.headers.get("content-type", "").split(";", 1)[0].lower() == "application/json":
        raise HTTPException(status_code=415, detail="JSON content type required")
    if beacon:
        validate_beacon_origin(request)
    else:
        validate_json_csrf(request)
    length = int(request.headers.get("content-length", "0") or 0)
    if length > 256_000:
        raise HTTPException(status_code=413, detail="Event batch is too large")
    try:
        raw_body = await request.body()
        if len(raw_body) > 256_000:
            raise HTTPException(status_code=413, detail="Event batch is too large")
        body = json.loads(raw_body)
        raw_events = body.get("events", [])
    except (json.JSONDecodeError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if not isinstance(raw_events, list) or not raw_events or len(raw_events) > settings.event_batch_max_size:
        raise HTTPException(status_code=422, detail="Event batch must contain 1 to 50 events")
    valid, errors = [], []
    for index, raw in enumerate(raw_events):
        try:
            valid.append((index, EventInput.model_validate(raw)))
        except ValueError as exc:
            if hasattr(exc, "errors"):
                msg = exc.errors()[0].get("msg", "")
                code = msg.replace("Value error, ", "").strip()
            else:
                code = str(exc).split("\n", 1)[0][:100]
            errors.append({"index": index, "code": code})
    user = await current_user(request, db)
    accepted, duplicates, service_errors = await ingest_events(db, valid, user_id=user.id if user else None, session_id=server_session_id(request.session))
    return {"accepted": accepted, "duplicates": duplicates, "rejected": len(errors) + len(service_errors), "errors": errors + service_errors}


@router.post("/batch")
async def batch(request: Request, db: AsyncSession = Depends(get_db)):
    return await _ingest(request, db)


@router.post("/beacon")
async def beacon(request: Request, db: AsyncSession = Depends(get_db)):
    return await _ingest(request, db, beacon=True)
