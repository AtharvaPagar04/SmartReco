from dataclasses import dataclass

from sqlalchemy import String, cast, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course
from app.schemas.search import SearchSuggestion
from app.search import escaped_like, normalize_search_query


@dataclass
class _SuggestionCourse:
    id: str
    title: str
    slug: str
    category: str
    tags: list[str]
    instructor: str
    is_featured: bool


async def get_search_suggestions(db: AsyncSession, query: str, limit: int = 8) -> list[SearchSuggestion]:
    query = normalize_search_query(query)
    if len(query) < 2:
        return []
    limit = min(max(limit, 1), 10)
    pattern, escape = escaped_like(query.lower())
    prefix = pattern[1:-1] + "%"
    lowered = func.lower
    tags_text = cast(Course.tags, String)
    rank = case(
        (lowered(Course.title) == query.lower(), 0),
        (lowered(Course.title).like(prefix, escape=escape), 1),
        (lowered(Course.category) == query.lower(), 2),
        (lowered(Course.category).like(prefix, escape=escape), 3),
        (lowered(tags_text).like(pattern, escape=escape), 4),
        (lowered(Course.instructor).like(prefix, escape=escape), 6),
        (lowered(Course.title).like(pattern, escape=escape), 7),
        (lowered(Course.category).like(pattern, escape=escape), 8),
        (lowered(Course.instructor).like(pattern, escape=escape), 10),
        else_=11,
    )
    matches = or_(
        lowered(Course.title).like(pattern, escape=escape),
        lowered(Course.category).like(pattern, escape=escape),
        lowered(tags_text).like(pattern, escape=escape),
        lowered(Course.instructor).like(pattern, escape=escape),
    )
    rows = (await db.execute(
        select(Course.id, Course.title, Course.slug, Course.category, Course.tags, Course.instructor, Course.is_featured)
        .where(Course.is_active.is_(True), matches)
        .order_by(rank, Course.is_featured.desc(), Course.title.asc(), Course.slug.asc())
        .limit(max(40, limit * 8))
    )).all()
    candidates: list[tuple[int, bool, str, str, SearchSuggestion]] = []
    needle = query.lower()
    labels: set[tuple[str, str]] = set()
    for row in rows:
        course = _SuggestionCourse(row[0], row[1], row[2], row[3], row[4] or [], row[5], row[6])
        title = course.title.lower()
        category = course.category.lower()
        instructor = course.instructor.lower()
        if needle in title:
            item_rank = 0 if title == needle else 1 if title.startswith(needle) else 7
            suggestion = SearchSuggestion(type="course", label=course.title, value=course.title, course_slug=course.slug, category=course.category)
            key = ("course", course.title.lower())
            if key not in labels:
                labels.add(key)
                candidates.append((item_rank, course.is_featured, course.title.lower(), course.slug, suggestion))
        if needle in category:
            item_rank = 2 if category == needle else 3 if category.startswith(needle) else 8
            suggestion = SearchSuggestion(type="category", label=course.category, value=course.category, category=course.category)
            key = ("category", category)
            if key not in labels:
                labels.add(key)
                candidates.append((item_rank, course.is_featured, category, course.slug, suggestion))
        for tag in course.tags:
            tag_text = str(tag).strip()
            tag_lower = tag_text.lower()
            if needle in tag_lower:
                item_rank = 4 if tag_lower == needle else 5 if tag_lower.startswith(needle) else 9
                suggestion = SearchSuggestion(type="tag", label=tag_text, value=tag_text, category=course.category)
                key = ("tag", tag_lower)
                if key not in labels:
                    labels.add(key)
                    candidates.append((item_rank, course.is_featured, tag_lower, course.slug, suggestion))
        if needle in instructor:
            item_rank = 6 if instructor.startswith(needle) else 10
            suggestion = SearchSuggestion(type="instructor", label=course.instructor, value=course.instructor, category=course.category)
            key = ("instructor", instructor)
            if key not in labels:
                labels.add(key)
                candidates.append((item_rank, course.is_featured, instructor, course.slug, suggestion))
    candidates.sort(key=lambda item: (item[0], not item[1], item[2], item[3]))
    return [item[-1] for item in candidates[:limit]]


async def public_by_slug(db: AsyncSession, slug: str) -> Course | None:
    return await db.scalar(select(Course).where(Course.slug == slug, Course.is_active.is_(True)))
