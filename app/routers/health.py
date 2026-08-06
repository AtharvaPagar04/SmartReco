import asyncio
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)):
    try:
        await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=2.0)
        return {"status": "ready", "database": "ok"}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": "error"},
        )
