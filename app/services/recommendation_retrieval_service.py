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
    path_role: str | None = None
    primary_affinity: float = 0.0
    secondary_affinity: float = 0.0
    goal_affinity: float = 0.0
    level_fit: float = 0.0
    path_score: float = 0.0


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


def _path_exclusions(profile: dict) -> set[str]:
    excluded = set(profile.get("excluded_course_ids", []))
    excluded.update(profile.get("recommendation_feedback", {}).get("excluded_course_ids", []))
    for key in ("enrolled_course_ids", "completed_course_ids", "purchased_unstarted_course_ids", "dismissed_course_ids"):
        excluded.update(profile.get(key, []))
    return excluded


async def retrieve_sql_learning_path_candidates(db: AsyncSession, profile: dict, *, limit: int) -> list[RecommendationCandidate]:
    excluded = _path_exclusions(profile)
    filters = [Course.is_active.is_(True)]
    if excluded:
        filters.append(Course.id.not_in(excluded))
    rows = list((await db.scalars(select(Course).where(*filters).order_by(Course.is_featured.desc(), Course.updated_at.desc(), Course.id.asc()).limit(limit))).all())
    return [RecommendationCandidate(course=course, retrieval_sources=["sql_fallback"], evidence={"fallback": True}) for course in rows]


import logging
import time

from app.services.learning_path_logging import LearningPathTraceContext, log_learning_path_step

logger = logging.getLogger(__name__)


async def retrieve_learning_path_candidates(
    db: AsyncSession,
    intent,
    profile: dict,
    *,
    limit: int,
    store: VectorStore | None = None,
    trace_context: LearningPathTraceContext | None = None,
    excluded: set[str] | None = None,
) -> tuple[list[RecommendationCandidate], bool, bool, list[str]]:
    """Retrieve multi-intent grounded candidates without changing recommendation retrieval."""
    from app.services.learning_path_intent import LearningPathIntent

    if not isinstance(intent, LearningPathIntent):
        raise TypeError("intent must be LearningPathIntent")

    trace_id = trace_context.trace_id if trace_context else "no_trace"
    excluded = _path_exclusions(profile) | set(excluded or ())

    t_q = time.perf_counter()
    queries = intent.retrieval_queries(profile)
    q_dur = (time.perf_counter() - t_q) * 1000
    query_types = [qtype for qtype, _ in queries]

    log_learning_path_step(
        logger,
        "learning_path.step.success",
        trace_id,
        step="retrieval.queries",
        duration_ms=q_dur,
        query_count=len(queries),
        query_types=query_types,
    )
    for qtype, qtext in queries:
        log_learning_path_step(
            logger,
            "learning_path.step.debug",
            trace_id,
            step="retrieval.query_preview",
            query_type=qtype,
            preview=qtext[:100],
        )

    candidates_by_id: dict[str, RecommendationCandidate] = {}
    semantic_used = False
    sql_used = False
    owned_store = store is None
    total_raw_hits = 0
    total_candidate_hits_before_dedup = 0

    if settings.mesh_api_key:
        store = store or VectorStore()
        try:
            for source, query in queries:
                log_learning_path_step(
                    logger,
                    "learning_path.step.start",
                    trace_id,
                    step="retrieval.embedding",
                    query_type=source,
                )
                t_emb = time.perf_counter()
                try:
                    vector = await embed_text(query)
                    emb_dur = (time.perf_counter() - t_emb) * 1000
                    log_learning_path_step(
                        logger,
                        "learning_path.step.success",
                        trace_id,
                        step="retrieval.embedding",
                        duration_ms=emb_dur,
                        query_type=source,
                        vector_dimensions=len(vector),
                    )
                except Exception as exc:
                    emb_dur = (time.perf_counter() - t_emb) * 1000
                    log_learning_path_step(
                        logger,
                        "learning_path.step.error",
                        trace_id,
                        step="retrieval.embedding",
                        duration_ms=emb_dur,
                        query_type=source,
                        exception_class=exc.__class__.__name__,
                        error_code="EMBEDDING_FAILED",
                    )
                    continue

                qdrant_limit = min(12, max(6, limit // 2))
                log_learning_path_step(
                    logger,
                    "learning_path.step.start",
                    trace_id,
                    step="retrieval.qdrant",
                    query_type=source,
                    limit=qdrant_limit,
                    collection=settings.qdrant_collection,
                )
                t_qdr = time.perf_counter()
                try:
                    hits = await store.search_courses(
                        vector,
                        limit=qdrant_limit,
                        filters={"is_active": True, "embedding_model": settings.mesh_embedding_model, "embedding_dimension": settings.vector_size, "embedding_schema_version": settings.embedding_schema_version},
                    )
                    qdr_dur = (time.perf_counter() - t_qdr) * 1000
                    log_learning_path_step(
                        logger,
                        "learning_path.step.success",
                        trace_id,
                        step="retrieval.qdrant",
                        duration_ms=qdr_dur,
                        query_type=source,
                        result_count=len(hits),
                    )
                except Exception as exc:
                    qdr_dur = (time.perf_counter() - t_qdr) * 1000
                    log_learning_path_step(
                        logger,
                        "learning_path.step.error",
                        trace_id,
                        step="retrieval.qdrant",
                        duration_ms=qdr_dur,
                        query_type=source,
                        exception_class=exc.__class__.__name__,
                        sanitized_message=str(exc)[:200],
                    )
                    continue

                semantic_used = True
                total_raw_hits += len(hits)
                ids = [hit.course_id for hit in hits if hit.course_id not in excluded]
                courses = {course.id: course for course in (await db.scalars(select(Course).where(Course.id.in_(ids), Course.is_active.is_(True)))).all()}
                for hit in hits:
                    course = courses.get(hit.course_id)
                    if not course:
                        continue
                    total_candidate_hits_before_dedup += 1
                    candidate = candidates_by_id.get(course.id)
                    if candidate is None:
                        candidate = RecommendationCandidate(course=course, semantic_score=float(hit.score), retrieval_sources=[], evidence={})
                        candidates_by_id[course.id] = candidate
                    elif candidate.semantic_score is None or float(hit.score) > candidate.semantic_score:
                        candidate.semantic_score = float(hit.score)
                    if source not in candidate.retrieval_sources:
                        candidate.retrieval_sources.append(f"qdrant:{source}")
                    candidate.evidence.setdefault("retrieval_queries", {})[source] = query
        finally:
            if owned_store and store is not None:
                store.close()

    log_learning_path_step(
        logger,
        "learning_path.step.success",
        trace_id,
        step="retrieval.qdrant_summary",
        semantic_retrieval_used=semantic_used,
        query_count=len(queries),
        raw_vector_candidate_count=total_raw_hits,
        unique_vector_candidate_count=len(candidates_by_id),
    )

    initial_vector_candidates_count = len(candidates_by_id)
    t_sql = time.perf_counter()

    if len(candidates_by_id) < limit or True:
        # Load all eligible active courses from SQL to evaluate catalog domain safety
        from app.services.learning_path_policy import ROLE_OUT_OF_DOMAIN, classify_course_for_path

        filters = [Course.is_active.is_(True)]
        if excluded:
            filters.append(Course.id.not_in(excluded))
        all_courses = list((await db.scalars(select(Course).where(*filters).order_by(Course.is_featured.desc(), Course.updated_at.desc(), Course.id.asc()))).all())

        added_catalog_safe = 0
        for course in all_courses:
            role, _ = classify_course_for_path(course, intent.primary_domain_code, intent.secondary_domain_codes)
            if role != ROLE_OUT_OF_DOMAIN:
                if course.id not in candidates_by_id:
                    candidates_by_id[course.id] = RecommendationCandidate(
                        course=course,
                        retrieval_sources=["sql_catalog"],
                        evidence={"catalog_safe": True},
                    )
                    sql_used = True
                    added_catalog_safe += 1

        added_fallback = 0
        if len(candidates_by_id) < limit:
            sql_used = True
            for course in all_courses:
                if course.id not in candidates_by_id:
                    candidates_by_id[course.id] = RecommendationCandidate(
                        course=course,
                        retrieval_sources=["sql_fallback"],
                        evidence={"fallback": True},
                    )
                    added_fallback += 1
                    if len(candidates_by_id) >= limit:
                        break

        total_sql_added = added_catalog_safe + added_fallback
        total_candidate_hits_before_dedup += total_sql_added
        if initial_vector_candidates_count == 0:
            sql_reason = "SEMANTIC_EMPTY"
        elif initial_vector_candidates_count < limit:
            sql_reason = "SEMANTIC_UNDER_TARGET"
        else:
            sql_reason = "DOMAIN_COVERAGE_SCAN"

        log_learning_path_step(
            logger,
            "learning_path.step.success",
            trace_id,
            step="retrieval.sql_expansion",
            duration_ms=(time.perf_counter() - t_sql) * 1000,
            reason=sql_reason,
            rows_scanned=len(all_courses),
            candidates_added=total_sql_added,
            total_candidates_after_sql=len(candidates_by_id),
        )

    duplicates_removed = max(0, total_candidate_hits_before_dedup - len(candidates_by_id))
    log_learning_path_step(
        logger,
        "learning_path.step.success",
        trace_id,
        step="candidates.deduplicate",
        before_count=total_candidate_hits_before_dedup,
        after_count=len(candidates_by_id),
        duplicates_removed=duplicates_removed,
    )

    return list(candidates_by_id.values()), semantic_used, sql_used, [query for _, query in queries]
