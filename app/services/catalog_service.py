from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course

VECTOR_FIELDS = ("title", "slug", "short_description", "description", "category", "tags", "price", "currency", "difficulty", "instructor", "duration_minutes", "is_active")


def apply_course_record(course: Course, values: dict) -> bool:
    vector_changed = any(getattr(course, field) != values[field] for field in VECTOR_FIELDS if field in values)
    for field, value in values.items():
        if hasattr(course, field):
            setattr(course, field, value)
    if vector_changed:
        course.version += 1
        course.vector_status = "PENDING" if course.is_active else "DELETING"
    return vector_changed

SORTS = {
    "newest": (Course.created_at.desc(), Course.id.asc()),
    "price_asc": (Course.price.asc(), Course.id.asc()),
    "price_desc": (Course.price.desc(), Course.id.asc()),
    "title": (Course.title.asc(), Course.id.asc()),
    "featured": (Course.is_featured.desc(), Course.created_at.desc(), Course.id.asc()),
}


def clean_page(value: int, size: int) -> tuple[int, int]:
    return max(1, value), min(max(1, size), 24)


async def list_courses(session: AsyncSession, *, query: str = "", category: str = "", difficulty: str = "", price: str = "", sort: str = "newest", page: int = 1, size: int = 12, active_only: bool = True):
    page, size = clean_page(page, size)
    filters = []
    if active_only:
        filters.append(Course.is_active.is_(True))
    if query.strip():
        q = f"%{' '.join(query.split())}%"
        filters.append(or_(Course.title.ilike(q), Course.short_description.ilike(q), Course.description.ilike(q), Course.category.ilike(q), Course.instructor.ilike(q), cast(Course.tags, String).ilike(q)))
    if category:
        filters.append(Course.category == category)
    if difficulty in {"BEGINNER", "INTERMEDIATE", "ADVANCED"}:
        filters.append(Course.difficulty == difficulty)
    if price == "free":
        filters.append(Course.price == 0)
    elif price == "paid":
        filters.append(Course.price > 0)
    where = and_(*filters) if filters else True
    total = await session.scalar(select(func.count(Course.id)).where(where)) or 0
    result = await session.execute(select(Course).where(where).order_by(*SORTS.get(sort, SORTS["newest"])).offset((page - 1) * size).limit(size))
    return list(result.scalars()), total, page, size


async def categories(session: AsyncSession) -> list[str]:
    return list((await session.execute(select(Course.category).where(Course.is_active.is_(True)).distinct().order_by(Course.category))).scalars())
