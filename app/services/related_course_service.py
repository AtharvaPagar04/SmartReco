from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Course, UserInterestProfile
from app.services.interest_profile_service import build_or_refresh_profile
from app.services.vector_store import VectorCourseHit, VectorStore, is_valid_vector

logger = logging.getLogger(__name__)
_cache: dict[str, tuple[float, tuple[tuple[str, str, float, float | None, bool, tuple[str, ...], str], ...]]] = {}


@dataclass(frozen=True)
class RelatedCourse:
    course: Course
    score: float
    semantic_score: float | None
    matched_category: bool
    matched_tags: tuple[str, ...]
    source: str
    reason: str = ""
    activity_score: float = 0.0
    context_score: float = 0.0
    difficulty_score: float = 0.0


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
    if value is None:
        return 0.0
    val = float(value)
    min_floor = getattr(settings, "related_courses_min_semantic_score", 0.45)
    if val < min_floor:
        return 0.0
    return max(0.0, min(1.0, val))


def _cache_key(course: Course, user_id: str | None = None) -> str:
    user_part = user_id or "anon"
    return ":".join(
        (
            user_part,
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
    if not is_valid_vector(vector):
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
        hits = await store.search_courses(
            vector,
            limit=settings.related_courses_candidate_limit,
            filters={
                "is_active": True,
                "embedding_model": settings.mesh_embedding_model,
                "embedding_dimension": settings.vector_size,
                "embedding_schema_version": settings.embedding_schema_version,
            },
        )
        min_floor = getattr(settings, "related_courses_min_semantic_score", 0.45)
        valid_hits = []
        for hit in hits:
            if hit.score >= min_floor and hit.payload and hit.payload.get("is_active") is True:
                valid_hits.append(hit)
        return valid_hits


async def _sql_candidates(db: AsyncSession, course: Course, excluded_course_ids: set[str] | None = None) -> list[Course]:
    category_first = case((Course.category == course.category, 0), else_=1)
    result = await db.scalars(
        select(Course)
        .where(Course.is_active.is_(True), Course.id != course.id, Course.id.not_in(excluded_course_ids or set()))
        .order_by(category_first, Course.is_featured.desc(), Course.updated_at.desc(), Course.slug.asc())
        .limit(max(50, settings.related_courses_candidate_limit * 5))
    )
    return list(result.all())


def _compute_activity_affinity(course: Course, profile: dict | None) -> tuple[float, str]:
    if not profile or not isinstance(profile, dict):
        return 0.0, ""
    confidence = float(profile.get("confidence", 0.0) or 0.0)
    if confidence <= 0.0:
        return 0.0, ""

    top_cats = profile.get("top_categories") or []
    cat_score = 0.0
    matched_cat_name = ""
    for item in top_cats:
        cat_name = item.get("name", "")
        if cat_name and cat_name.casefold() == course.category.casefold():
            cat_score = float(item.get("score", 0.0))
            matched_cat_name = cat_name
            break

    top_tags = profile.get("top_tags") or []
    c_tags = _tags(course)
    tag_score = 0.0
    matched_tag_name = ""
    if c_tags and top_tags:
        for item in top_tags:
            tag_name = str(item.get("name", "")).strip()
            if tag_name.casefold() in c_tags:
                sc = float(item.get("score", 0.0))
                if sc > tag_score:
                    tag_score = sc
                    matched_tag_name = tag_name

    raw_affinity = 0.6 * cat_score + 0.4 * tag_score
    affinity = raw_affinity * confidence

    signal_text = ""
    if matched_tag_name:
        signal_text = matched_tag_name
    elif matched_cat_name:
        signal_text = matched_cat_name

    return min(1.0, max(0.0, affinity)), signal_text


def _generate_reason(
    course: Course,
    current: Course,
    same_category: bool,
    overlap_tags: tuple[str, ...],
    semantic_score_val: float | None,
    activity_affinity: float,
    activity_signal: str,
) -> str:
    min_floor = getattr(settings, "related_courses_min_semantic_score", 0.45)
    valid_semantic = semantic_score_val is not None and semantic_score_val >= min_floor

    if activity_affinity >= 0.10 and activity_signal:
        if same_category:
            return f"Related to the {course.category} concepts in this course and matches your recent {activity_signal} learning activity."
        else:
            return f"Connects to this course and matches your recent {activity_signal} learning activity."

    if valid_semantic and overlap_tags:
        tag_str = ", ".join(overlap_tags[:2])
        return f"Related to the {tag_str} concepts in this course."
    elif valid_semantic:
        return f"Shares core conceptual foundations with '{current.title}'."
    elif same_category:
        return f"Explores additional topics in {course.category}."
    elif overlap_tags:
        return f"Shares key topics ({', '.join(overlap_tags[:2])}) with this course."
    else:
        return f"Provides relevant continuing material in {course.category}."


def _rank(
    current: Course,
    candidates: list[_Candidate],
    limit: int,
    profile: dict | None = None,
) -> list[RelatedCourse]:
    current_tags = _tags(current)
    ranked: list[RelatedCourse] = []

    sem_w = getattr(settings, "related_courses_semantic_weight", 0.45)
    cat_w = getattr(settings, "related_courses_category_weight", 0.15)
    tag_w = getattr(settings, "related_courses_tag_weight", 0.10)
    act_w = getattr(settings, "related_courses_activity_weight", 0.25)
    diff_w = getattr(settings, "related_courses_difficulty_weight", 0.05)

    for candidate in candidates:
        course_tags = _tags(candidate.course)
        union = current_tags | course_tags
        overlap = current_tags & course_tags
        tag_jaccard = len(overlap) / len(union) if union else 0.0
        same_category = current.category.casefold() == candidate.course.category.casefold()

        # Hard relevance gate: candidate MUST be relevant to current course
        sem_val = _semantic_score(candidate.semantic_score)
        valid_sem = sem_val > 0.0
        is_relevant = same_category or (len(overlap) > 0) or valid_sem
        if not is_relevant:
            continue

        act_affinity, act_signal = _compute_activity_affinity(candidate.course, profile)
        diff_fit = _difficulty_score(current.difficulty, candidate.course.difficulty)

        if valid_sem:
            context_score = (sem_w * sem_val) + (cat_w * float(same_category)) + (tag_w * tag_jaccard)
        else:
            context_score = ((sem_w + cat_w) * float(same_category)) + ((tag_w + sem_w * 0.5) * tag_jaccard)

        total_score = context_score + (act_w * act_affinity) + (diff_w * diff_fit)
        final_score = max(0.0, min(1.0, total_score))

        reason = _generate_reason(
            candidate.course,
            current,
            same_category,
            tuple(sorted(overlap)),
            candidate.semantic_score,
            act_affinity,
            act_signal,
        )

        ranked.append(
            RelatedCourse(
                course=candidate.course,
                score=final_score,
                semantic_score=candidate.semantic_score,
                matched_category=same_category,
                matched_tags=tuple(sorted(overlap)),
                source=candidate.source,
                reason=reason,
                activity_score=act_affinity,
                context_score=context_score,
                difficulty_score=diff_fit,
            )
        )

    ranked.sort(
        key=lambda item: (
            -item.score,
            -_semantic_score(item.semantic_score),
            not item.course.is_featured,
            item.course.slug,
            item.course.id,
        )
    )

    if not ranked:
        return []

    selected = [ranked[0]]
    for item in ranked[1:]:
        first_tags = _tags(selected[0].course)
        near_duplicate = (
            item.course.category.casefold() == selected[0].course.category.casefold()
            and len(first_tags | _tags(item.course)) > 0
            and len(first_tags & _tags(item.course)) / len(first_tags | _tags(item.course)) >= 0.8
        )
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
        RelatedCourse(
            course=by_id[course_id],
            score=score,
            semantic_score=semantic_score,
            matched_category=matched_category,
            matched_tags=matched_tags,
            source=source,
            reason=reason,
        )
        for course_id, source, score, semantic_score, matched_category, matched_tags, reason in entry[1][:limit]
    ]


async def get_related_courses(
    db: AsyncSession,
    course: Course,
    *,
    limit: int = 2,
    user_id: str | None = None,
    profile: dict | None = None,
    store: VectorStore | None = None,
    excluded_course_ids: set[str] | None = None,
) -> list[RelatedCourse]:
    if not settings.related_courses_enabled or limit <= 0:
        return []
    limit = min(limit, settings.related_courses_limit)
    key = _cache_key(course, user_id)
    excluded_course_ids = excluded_course_ids or set()
    cached = None if excluded_course_ids or user_id else await _cached(db, course, key, limit)
    if cached:
        return cached

    profile_dict: dict | None = profile
    if profile_dict is None and user_id:
        try:
            profile_obj = await db.scalar(select(UserInterestProfile).where(UserInterestProfile.user_id == user_id))
            if profile_obj:
                profile_dict = profile_obj.profile_json
            else:
                profile_record = await build_or_refresh_profile(db, user_id)
                profile_dict = profile_record.profile_json if profile_record else None
        except Exception as exc:
            logger.info("failed to load user interest profile for related courses", extra={"user_id": user_id, "error_category": type(exc).__name__})
            profile_dict = None

    logger.info(
        "related_courses.request.start",
        extra={
            "current_course_id": course.id,
            "current_category": course.category,
            "user_id": user_id,
            "authenticated": bool(user_id),
            "profile_available": bool(profile_dict),
        },
    )

    semantic: list[VectorCourseHit] = []
    used_semantic = False
    try:
        semantic = await _semantic_candidates(course, store or VectorStore())
        used_semantic = bool(semantic)
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
    used_sql = False
    if len(candidates) < limit * 3:
        used_sql = True
        fallback_rows = await _sql_candidates(db, course, excluded_course_ids)
        existing = {candidate.course.id for candidate in candidates}
        candidates.extend(_Candidate(row, None, "sql") for row in fallback_rows if row.id not in existing and row.id != course.id)

    result = _rank(course, candidates, limit, profile=profile_dict)

    logger.info(
        "related_courses.request.success",
        extra={
            "current_course_id": course.id,
            "semantic_used": used_semantic,
            "sql_fallback_used": used_sql,
            "candidate_count": len(candidates),
            "selected_count": len(result),
            "selected_ids": [item.course.id for item in result],
        },
    )

    if not user_id and not excluded_course_ids:
        _cache[key] = (
            time.monotonic() + settings.related_courses_cache_ttl_seconds,
            tuple(
                (item.course.id, item.source, item.score, item.semantic_score, item.matched_category, item.matched_tags, item.reason)
                for item in result
            ),
        )
        if len(_cache) > 256:
            oldest = min(_cache, key=lambda k: _cache[k][0])
            _cache.pop(oldest, None)

    return result
