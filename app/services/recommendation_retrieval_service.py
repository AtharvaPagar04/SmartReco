from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Course
from app.services.embedding_service import embed_text
from app.services.vector_store import VectorCourseHit, VectorStore


@dataclass
class RecommendationCandidate:
    course: Course
    semantic_score: float | None = None
    category_affinity: float = 0.0
    tag_affinity: float = 0.0
    search_affinity: float = 0.0
    dwell_affinity: float = 0.0
    novelty_score: float = 1.0
    featured_boost: float = 0.0
    recently_viewed_penalty: float = 0.0
    base_personalized_score: float = 0.0
    feedback_adjustment: float = 0.0
    feedback_score: float = 0.0
    deterministic_score: float = 0.0
    retrieval_sources: list[str] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)


def build_retrieval_query(profile: dict) -> str:
    categories = ", ".join(item["name"] for item in profile.get("top_categories", [])[:4])
    tags = ", ".join(item["name"] for item in profile.get("top_tags", [])[:6])
    terms = ", ".join(item["term"] for item in profile.get("top_search_terms", [])[:4])
    return f"Interested in {categories or 'practical learning'}, {tags or 'useful skills'}, and searches for {terms or 'new courses'}."


async def _sql_candidates(db: AsyncSession, profile: dict, limit: int) -> list[RecommendationCandidate]:
    terms = [item["term"] for item in profile.get("top_search_terms", [])[:5]]
    categories = [item["name"] for item in profile.get("top_categories", [])[:5]]
    tags = [item["name"] for item in profile.get("top_tags", [])[:8]]
    clauses = [Course.is_featured.is_(True)]
    for value in [*terms, *categories, *tags]:
        pattern = f"%{' '.join(value.split())}%"
        clauses.append(or_(Course.title.ilike(pattern), Course.category.ilike(pattern), cast(Course.tags, String).ilike(pattern), Course.instructor.ilike(pattern)))
    excluded = set(profile.get("excluded_course_ids", []))
    excluded.update(profile.get("recommendation_feedback", {}).get("excluded_course_ids", []))
    for key in ("enrolled_course_ids", "completed_course_ids", "purchased_unstarted_course_ids", "dismissed_course_ids"):
        excluded.update(profile.get(key, []))
    filters = [Course.is_active.is_(True), or_(*clauses)]
    if excluded:
        filters.append(Course.id.not_in(excluded))
    rows = list((await db.execute(select(Course).where(*filters).order_by(Course.is_featured.desc(), Course.updated_at.desc(), Course.id.asc()).limit(limit))).scalars())
    if len(rows) < limit:
        extra_filters = [Course.is_active.is_(True), Course.id.not_in([course.id for course in rows])]
        if excluded:
            extra_filters.append(Course.id.not_in(excluded))
        extra = list((await db.execute(select(Course).where(*extra_filters).order_by(Course.is_featured.desc(), Course.updated_at.desc(), Course.id.asc()).limit(limit - len(rows)))).scalars())
        rows.extend(extra)
    return [RecommendationCandidate(course=course, retrieval_sources=["sql_fallback"], evidence={"fallback": True}) for course in rows]


async def retrieve_candidates(db: AsyncSession, profile: dict, *, limit: int | None = None, store: VectorStore | None = None) -> tuple[list[RecommendationCandidate], bool, bool]:
    limit = limit or settings.recommendation_max_candidates
    if profile.get("confidence", 0) < 0.26 or not settings.mesh_api_key:
        return await _sql_candidates(db, profile, limit), False, True
    store = store or VectorStore()
    try:
        vector = await embed_text(build_retrieval_query(profile))
        hits = await store.search_courses(vector, limit=limit, filters={"is_active": True, "embedding_model": settings.mesh_embedding_model, "embedding_dimension": settings.vector_size, "embedding_schema_version": settings.embedding_schema_version})
        ids = [hit.course_id for hit in hits]
        courses = {course.id: course for course in (await db.scalars(select(Course).where(Course.id.in_(ids), Course.is_active.is_(True)))).all()}
        candidates = []
        for hit in hits:
            course = courses.get(hit.course_id)
            excluded = set(profile.get("excluded_course_ids", []))
            excluded.update(profile.get("recommendation_feedback", {}).get("excluded_course_ids", []))
            for key in ("enrolled_course_ids", "completed_course_ids", "purchased_unstarted_course_ids", "dismissed_course_ids"):
                excluded.update(profile.get(key, []))
            if course and course.id not in excluded:
                candidates.append(RecommendationCandidate(course=course, semantic_score=float(hit.score), retrieval_sources=["qdrant_semantic"], evidence={"semantic_score": float(hit.score)}))
        if len(candidates) >= 3:
            return candidates, True, False
    except Exception:
        pass
    return await _sql_candidates(db, profile, limit), False, True


async def retrieve_sql_fallback(db: AsyncSession, profile: dict, *, limit: int | None = None) -> list[RecommendationCandidate]:
    return await _sql_candidates(db, profile, limit or settings.recommendation_max_candidates)
