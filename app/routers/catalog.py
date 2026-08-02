from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Course
from app.repositories.courses import public_by_slug
from app.routers.helpers import page
from app.security import current_user
from app.services.catalog_service import categories, list_courses

router = APIRouter()


@router.get("/")
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    user = await current_user(request, db)
    featured = list((await db.execute(select(Course).where(Course.is_active.is_(True), Course.is_featured.is_(True)).order_by(Course.created_at.desc()).limit(6))).scalars())
    return page(request, "home.html", current_user=user, featured=featured, categories=await categories(db))


@router.get("/courses")
async def course_catalog(request: Request, q: str = Query("", max_length=200), category: str = Query("", max_length=80), difficulty: str = Query("", max_length=20), price: str = Query("", max_length=10), sort: str = Query("newest", max_length=20), page_number: int = Query(1, alias="page", ge=1), size: int = Query(12, ge=1, le=24), db: AsyncSession = Depends(get_db)):
    user = await current_user(request, db)
    courses, total, page_number, size = await list_courses(db, query=q, category=category, difficulty=difficulty, price=price, sort=sort, page=page_number, size=size)
    return page(request, "catalog/list.html", current_user=user, courses=courses, total=total, page=page_number, size=size, pages=(total + size - 1) // size, q=q, category=category, difficulty=difficulty, price=price, sort=sort, categories=await categories(db))


@router.get("/courses/{slug}")
async def course_detail(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    course = await public_by_slug(db, slug)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return page(request, "catalog/detail.html", current_user=await current_user(request, db), course=course)
