from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Course
from app.services.vector_store import VectorCourseHit, VectorStore

logger = logging.getLogger(__name__)
_cache: dict[str, tuple[float, tuple[tuple[str, str, float, float | None, bool, tuple[str, ...]], ...]]] = {}


@dataclass(frozen=True)
class RelatedCourse:
    course: Course
    score: float
    semantic_score: float | None
    matched_category: bool
    matched_tags: tuple[str, ...]
    source: str


@dataclass(frozen=True)
class _Candidate:
    course: Course
    semantic_score: float | None
    source: str


def _tags(course: Course) -> set[str]:
    return {str(tag).strip().casefold() for tag in (course.tags or []) if str(tag).strip()}


def _difficulty_score(left: str, right: str) -> float:
    order = {"BEGINNER": 0, "INTERMEDIATE": 1, "ADVANCED": 2}
    distance = abs(order.get(left.upper(), 1) - order.get(right.upper(), 1))
    return 1.0 if distance == 0 else 0.5 if distance == 1 else 0.0


def _semantic_score(value: float | None) -> float:
    return max(0.0, min(1.0, float(value or 0.0)))


def _cache_key(course: Course) -> str:
    return ":".join(
        (
            course.id,
            str(course.version),
            settings.mesh_embedding_model,
            str(settings.embedding_schema_version),
            str(settings.related_courses_candidate_limit),
        )
    )


def _valid_lineage(payload: dict, course: Course) -> bool:
    return (
        payload.get("course_id") == course.id
        and payload.get("is_active") is True
        and payload.get("version") == course.version
        and payload.get("embedding_model") == settings.mesh_embedding_model
        and payload.get("embedding_dimension") == settings.vector_size
        and payload.get("embedding_schema_version") == settings.embedding_schema_version
    )


def _point_vector(point) -> list[float] | None:
    vector = getattr(point, "vector", None)
    if isinstance(vector, dict):
        vector = next(iter(vector.values()), None)
    if not isinstance(vector, list) or not vector:
        return None
    return vector


async def _semantic_candidates(course: Course, store: VectorStore) -> list[VectorCourseHit]:
    async with asyncio.timeout(settings.related_courses_timeout_seconds):
        point = await store.get_point(course.id, with_vectors=True)
        if not point or not _valid_lineage(point.payload or {}, course):
            return []
        vector = _point_vector(point)
        if not vector:
            return []
        return await store.search_courses(
            vector,
            limit=settings.related_courses_candidate_limit,
            filters={
                "is_active": True,
                "embedding_model": settings.mesh_embedding_model,
                "embedding_dimension": settings.vector_size,
                "embedding_schema_version": settings.embedding_schema_version,
            },
        )


async def _sql_candidates(db: AsyncSession, course: Course, excluded_course_ids: set[str] | None = None) -> list[Course]:
    category_first = case((Course.category == course.category, 0), else_=1)
    result = await db.scalars(
        select(Course)
        .where(Course.is_active.is_(True), Course.id != course.id, Course.id.not_in(excluded_course_ids or set()))
        .order_by(category_first, Course.is_featured.desc(), Course.updated_at.desc(), Course.slug.asc())
        .limit(max(50, settings.related_courses_candidate_limit * 5))
    )
    return list(result.all())


def _rank(current: Course, candidates: list[_Candidate], limit: int) -> list[RelatedCourse]:
    current_tags = _tags(current)
    ranked: list[RelatedCourse] = []
    for candidate in candidates:
        course_tags = _tags(candidate.course)
        union = current_tags | course_tags
        overlap = current_tags & course_tags
        tag_score = len(overlap) / len(union) if union else 0.0
        same_category = current.category.casefold() == candidate.course.category.casefold()
        score = (
            settings.related_courses_semantic_weight * _semantic_score(candidate.semantic_score)
            + settings.related_courses_category_weight * float(same_category)
            + settings.related_courses_tag_weight * tag_score
            + settings.related_courses_difficulty_weight * _difficulty_score(current.difficulty, candidate.course.difficulty)
        )
        ranked.append(RelatedCourse(candidate.course, max(0.0, min(1.0, score)), candidate.semantic_score, same_category, tuple(sorted(overlap)), candidate.source))

    ranked.sort(key=lambda item: (-item.score, -_semantic_score(item.semantic_score), not item.course.is_featured, item.course.slug, item.course.id))
    if not ranked:
        return []
    selected = [ranked[0]]
    for item in ranked[1:]:
        first_tags = _tags(selected[0].course)
        near_duplicate = item.course.category.casefold() == selected[0].course.category.casefold() and len(first_tags | _tags(item.course)) > 0 and len(first_tags & _tags(item.course)) / len(first_tags | _tags(item.course)) >= 0.8
        adjusted = item.score - 0.05 if near_duplicate else item.score
        if adjusted > 0 or len(selected) < limit:
            selected.append(item)
        if len(selected) == limit:
            break
    return selected[:limit]


async def _cached(db: AsyncSession, course: Course, key: str, limit: int) -> list[RelatedCourse] | None:
    entry = _cache.get(key)
    if not entry or entry[0] <= time.monotonic():
        _cache.pop(key, None)
        return None
    ids = [course_id for course_id, *_ in entry[1]]
    rows = list((await db.scalars(select(Course).where(Course.id.in_(ids), Course.is_active.is_(True)))).all()) if ids else []
    by_id = {row.id: row for row in rows}
    if len(by_id) != len(ids):
        return None
    return [
        RelatedCourse(by_id[course_id], score, semantic_score, matched_category, matched_tags, source)
        for course_id, source, score, semantic_score, matched_category, matched_tags in entry[1][:limit]
    ]


async def get_related_courses(db: AsyncSession, course: Course, *, limit: int = 2, store: VectorStore | None = None, excluded_course_ids: set[str] | None = None) -> list[RelatedCourse]:
    if not settings.related_courses_enabled or limit <= 0:
        return []
    limit = min(limit, settings.related_courses_limit)
    key = _cache_key(course)
    excluded_course_ids = excluded_course_ids or set()
    cached = None if excluded_course_ids else await _cached(db, course, key, limit)
    if cached:
        return cached

    semantic: list[VectorCourseHit] = []
    try:
        semantic = await _semantic_candidates(course, store or VectorStore())
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.info("contextual semantic lookup unavailable", extra={"course_id": course.id, "error_category": type(exc).__name__})

    ids = {course.id}
    semantic_scores: dict[str, float] = {}
    semantic_candidates: list[_Candidate] = []
    for hit in semantic:
        if hit.course_id in ids or hit.course_id in excluded_course_ids:
            continue
        ids.add(hit.course_id)
        semantic_scores[hit.course_id] = hit.score
    if semantic_scores:
        rows = list((await db.scalars(select(Course).where(Course.id.in_(semantic_scores), Course.is_active.is_(True)))).all())
        by_id = {row.id: row for row in rows}
        semantic_candidates = [_Candidate(by_id[course_id], semantic_scores[course_id], "semantic") for course_id in semantic_scores if course_id in by_id]

    candidates = semantic_candidates
    if len(candidates) < limit:
        fallback_rows = await _sql_candidates(db, course, excluded_course_ids)
        existing = {candidate.course.id for candidate in candidates}
        candidates.extend(_Candidate(row, None, "sql") for row in fallback_rows if row.id not in existing and row.id != course.id)

    result = _rank(course, candidates, limit)
    _cache[key] = (
        time.monotonic() + settings.related_courses_cache_ttl_seconds,
        tuple((item.course.id, item.source, item.score, item.semantic_score, item.matched_category, item.matched_tags) for item in result),
    )
    if len(_cache) > 256:
        oldest = min(_cache, key=lambda item: _cache[item][0])
        _cache.pop(oldest, None)
    return result
