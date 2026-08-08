from __future__ import annotations

import math
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models import Course, LearningPath, LearningPathGenerationRun, LearningPathItem, LearningPathStatus, User
from app.schemas.learning_path import DOMAIN_BY_CODE, LearningPathInput
from app.services.interest_profile_service import build_or_refresh_profile
from app.services.learning_path_intent import LearningPathIntent
from app.services.learning_path_planner import (
    PlanGenerationResult,
    generate_plan_with_repairs,
    pre_rank_candidates,
    select_fallback_courses,
)
from app.services.learning_path_policy import MAX_PATH_COURSES, MIN_PATH_COURSES, ROLE_OUT_OF_DOMAIN
from app.services.langsmith_service import trace_metadata, tracing_enabled
from app.services.recommendation_retrieval_service import (
    RecommendationCandidate,
    retrieve_learning_path_candidates,
)


STAGES = (
    "Build the foundation",
    "Strengthen the core skill",
    "Apply the skill",
    "Build production confidence",
    "Extend your capability",
    "Practice at depth",
    "Complete a capstone step",
    "Keep progressing",
)
DIFFICULTY = {"BEGINNER": 0, "INTERMEDIATE": 1, "ADVANCED": 2}


def _hours(course: Course) -> int:
    return max(1, math.ceil(course.total_curriculum_minutes / 60))


def _profile_for_input(path_input: LearningPathInput, profile: dict) -> dict:
    """Build compatibility context without turning known skills into targets."""
    intent = LearningPathIntent.from_input(path_input)
    domains = [DOMAIN_BY_CODE[path_input.primary_domain], *(DOMAIN_BY_CODE[code] for code in path_input.secondary_domains)]
    merged = dict(profile)
    merged["top_categories"] = [{"name": category} for domain in domains for category in domain.categories] + profile.get("top_categories", [])[:3]
    merged["top_tags"] = [{"name": tag} for domain in domains for tag in domain.tags] + profile.get("top_tags", [])[:5]
    merged["top_search_terms"] = [{"term": value} for value in (*intent.goal_labels, *intent.learning_preference_labels, *intent.format_labels)] + profile.get("top_search_terms", [])[:3]
    if path_input.optional_instruction:
        merged["top_search_terms"].append({"term": path_input.optional_instruction})
    merged["confidence"] = 1.0
    merged["learning_path_intent"] = intent.to_prompt_dict()
    return merged


def _score(course: Course, path_input: LearningPathInput, profile: dict) -> float:
    """Compatibility score for callers; V2 uses normalized pre-ranking."""
    intent = LearningPathIntent.from_input(path_input)
    candidate = RecommendationCandidate(course=course)
    return pre_rank_candidates([candidate], intent, profile)[0].path_score


def _select_courses(candidates: list[RecommendationCandidate], path_input: LearningPathInput, profile: dict) -> list[Course]:
    """Compatibility wrapper for the explicit deterministic V2 fallback."""
    return select_fallback_courses(candidates, LearningPathIntent.from_input(path_input), profile)


def _fallback_reason(course: Course, domain_label: str) -> str:
    skills = ", ".join((course.what_you_will_learn or course.tags or [])[:3]) or course.category
    return f"{course.title} is a grounded fallback stage for {domain_label}, focusing on {skills}."


async def candidate_courses(db: AsyncSession, user: User, path_input: LearningPathInput) -> tuple[list[RecommendationCandidate], str | None, dict]:
    profile_row = await build_or_refresh_profile(db, user.id)
    profile = _profile_for_input(path_input, profile_row.profile_json or {})
    intent = LearningPathIntent.from_input(path_input)
    limit = max(settings.learning_path_max_candidates, intent.requested_course_count * 3)
    candidates, semantic_used, sql_used, queries = await retrieve_learning_path_candidates(db, intent, profile, limit=limit)
    return candidates, profile_row.profile_hash, {
        "semantic_retrieval_used": semantic_used,
        "sql_fallback_used": sql_used,
        "retrieval_queries": queries,
        "candidate_limit": limit,
    }


async def _reload_selected_courses(db: AsyncSession, plan: PlanGenerationResult) -> list[tuple[object, Course]]:
    ids = [stage.course_id for stage in plan.plan.stages]
    rows = list((await db.scalars(select(Course).where(Course.id.in_(ids), Course.is_active.is_(True)))).all()) if ids else []
    courses = {course.id: course for course in rows}
    return [(stage, courses[stage.course_id]) for stage in plan.plan.stages if stage.course_id in courses]


async def create_learning_path(db: AsyncSession, user: User, path_input: LearningPathInput, *, status: str = "READY") -> LearningPath:
    intent = LearningPathIntent.from_input(path_input)
    profile_row = await build_or_refresh_profile(db, user.id)
    profile = _profile_for_input(path_input, profile_row.profile_json or {})
    limit = max(settings.learning_path_max_candidates, intent.requested_course_count * 3)
    trace_id = None
    if tracing_enabled():
        try:
            from langsmith import trace
        except Exception:
            trace = None
        if trace:
            with trace(name="smartreco-learning-path", project_name=settings.langsmith_project, metadata={
                **trace_metadata(user_id=user.id, trigger_type="learning_path", profile_version=profile_row.version, candidate_count=0),
                "path_length": intent.path_length,
                "requested_course_count": intent.requested_course_count,
                "primary_domain_code": intent.primary_domain_code,
                "secondary_domain_count": len(intent.secondary_domain_codes),
                "goal_count": len(intent.goal_codes),
            }) as span:
                candidates, semantic_used, sql_used, queries = await retrieve_learning_path_candidates(db, intent, profile, limit=limit)
                plan_result = await generate_plan_with_repairs(intent, candidates, profile)
                trace_id = str(getattr(span, "id", "")) or None
        else:
            candidates, semantic_used, sql_used, queries = await retrieve_learning_path_candidates(db, intent, profile, limit=limit)
            plan_result = await generate_plan_with_repairs(intent, candidates, profile)
    else:
        candidates, semantic_used, sql_used, queries = await retrieve_learning_path_candidates(db, intent, profile, limit=limit)
        plan_result = await generate_plan_with_repairs(intent, candidates, profile)
    selected = await _reload_selected_courses(db, plan_result)
    courses = [course for _, course in selected]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    total_minutes = sum(course.total_curriculum_minutes for course in courses)
    total_price = sum((Decimal(str(course.price)) for course in courses), Decimal("0.00"))
    total_hours = max(1, math.ceil(total_minutes / 60)) if courses else 0
    weeks = math.ceil(total_minutes / (path_input.weekly_hours * 60)) if courses else 0

    coverage = plan_result.coverage
    effective_count = coverage.effective_target_count if coverage else len(courses)
    requested_count = coverage.requested_count if coverage else intent.requested_course_count
    coverage_limited = coverage.coverage_limited if coverage else False
    coverage_reason = coverage.coverage_reason if coverage else None

    available_safe_count = coverage.available_safe_count if coverage else len(courses)
    valid_statuses = {"VALID", "VALID_COVERAGE_LIMITED", "REPAIRED_VALID", "REPAIRED_COVERAGE_LIMITED", "FALLBACK_VALID", "FALLBACK_COVERAGE_LIMITED"}

    plan_is_valid = (
        len(courses) == effective_count
        and effective_count >= MIN_PATH_COURSES
        and plan_result.validation_status in valid_statuses
    )

    if available_safe_count < MIN_PATH_COURSES or plan_result.validation_status == "INSUFFICIENT_COVERAGE":
        final_status = LearningPathStatus.INSUFFICIENT_COVERAGE
    elif plan_is_valid:
        final_status = status
    else:
        final_status = LearningPathStatus.FAILED

    is_valid = plan_is_valid and final_status in {LearningPathStatus.READY, LearningPathStatus.DRAFT}

    metadata = {
        "semantic_retrieval_used": semantic_used,
        "sql_fallback_used": sql_used,
        "llm_attempted": plan_result.llm_attempted,
        "llm_failure_reason": plan_result.llm_failure_reason,
        "llm_generation_used": plan_result.llm_generation_used,
        "llm_repair_used": plan_result.repair_count > 0,
        "llm_repair_count": plan_result.repair_count,
        "deterministic_fallback_used": plan_result.deterministic_fallback_used,
        "generation_model": (settings.learning_path_chat_model or settings.mesh_chat_model) if plan_result.llm_generation_used else None,
        "validation_status": plan_result.validation_status,
        "candidate_limit": settings.learning_path_max_candidates,
        "prompt_candidate_count": plan_result.prompt_candidate_count,
        "retrieval_candidate_count": len(candidates),
        "retrieval_query_count": len(queries),
        "primary_domain_code": intent.primary_domain_code,
        "secondary_domain_count": len(intent.secondary_domain_codes),
        "goal_count": len(intent.goal_codes),
        "trace_id": trace_id,
        "path_mode": intent.path_length,
        "auto_min": MIN_PATH_COURSES if intent.path_length == "AUTO" else None,
        "auto_max": MAX_PATH_COURSES if intent.path_length == "AUTO" else None,
        "requested_count": requested_count,
        "available_safe_count": available_safe_count,
        "effective_target_count": effective_count,
        "selected_count": len(courses) if is_valid else 0,
        "coverage_limited": coverage_limited,
        "coverage_reason": coverage_reason,
        "coverage_status": "INSUFFICIENT" if available_safe_count < MIN_PATH_COURSES else ("LIMITED" if coverage_limited else "SUFFICIENT"),
        "explanation_source": "MESH" if plan_result.llm_generation_used else "FALLBACK",
        "failure_reason": None if is_valid else (plan_result.validation_status if plan_result.validation_status != "INSUFFICIENT_COVERAGE" else "INSUFFICIENT_CATALOG_COVERAGE"),
    }
    path = LearningPath(
        user_id=user.id,
        title=plan_result.plan.title,
        summary=f"{plan_result.plan.summary} {plan_result.plan.final_outcome}".strip(),
        status=final_status,
        primary_domain=path_input.primary_domain,
        secondary_domains_json=path_input.secondary_domains,
        goal_code=path_input.goal,
        level_code=path_input.level,
        learning_preferences_json=path_input.learning_preferences,
        weekly_hours=path_input.weekly_hours,
        target_weeks=path_input.target_weeks,
        budget_type=path_input.budget_type,
        budget_scope=path_input.budget_scope,
        budget_amount=path_input.effective_budget(),
        currency=path_input.currency,
        path_length_preference=path_input.path_length,
        optional_instruction=path_input.optional_instruction or None,
        input_json=path_input.model_dump(mode="json"),
        prompt_version=settings.learning_path_prompt_version,
        profile_hash=profile_row.profile_hash,
        # Historical compatibility: used_mesh means semantic retrieval succeeded.
        used_mesh=semantic_used,
        used_fallback=sql_used or plan_result.deterministic_fallback_used,
        estimated_total_hours=total_hours if is_valid else 0,
        estimated_weeks=weeks if is_valid else 0,
        total_price=total_price if is_valid else Decimal("0.00"),
        generated_at=now,
    )
    db.add(path)
    await db.flush()
    if is_valid:
        for index, (stage, course) in enumerate(selected, 1):
            following = courses[index] if index < len(courses) else None
            next_text = stage.how_it_leads_forward or (f"This stage prepares you for {following.title}." if following else f"This stage advances the {intent.primary_domain_label} outcome.")
            db.add(LearningPathItem(
                learning_path_id=path.id,
                course_id=course.id,
                position=index,
                stage_label=STAGES[min(index - 1, len(STAGES) - 1)],
                reason=stage.why_this_course or _fallback_reason(course, intent.primary_domain_label),
                how_it_prepares_next=next_text,
                skills_gained_json=list((course.what_you_will_learn or course.tags or [])[:5]),
                estimated_hours=_hours(course),
                price_snapshot=course.price,
                currency=course.currency,
            ))

    db.add(LearningPathGenerationRun(
        learning_path_id=path.id,
        status="SUCCEEDED" if is_valid else "FAILED",
        candidate_count=len(candidates),
        selected_count=len(courses),
        used_fallback=sql_used or plan_result.deterministic_fallback_used,
        metadata_json=metadata,
        started_at=now,
        completed_at=now,
    ))
    await db.flush()
    return path


async def get_owned_path(db: AsyncSession, user_id: str, path_id: str) -> LearningPath | None:
    return await db.scalar(
        select(LearningPath)
        .options(
            selectinload(LearningPath.items).selectinload(LearningPathItem.course),
            selectinload(LearningPath.generation_runs),
        )
        .where(LearningPath.id == path_id, LearningPath.user_id == user_id)
    )



async def replace_item(db: AsyncSession, path: LearningPath, item: LearningPathItem, reason: str) -> bool:
    path_input = LearningPathInput.model_validate(path.input_json)
    user = await db.scalar(select(User).where(User.id == path.user_id))
    if not user:
        return False
    candidates, _, _ = await candidate_courses(db, user, path_input)
    intent = LearningPathIntent.from_input(path_input)
    excluded = {path_item.course_id for path_item in path.items}
    ranked = [candidate for candidate in pre_rank_candidates(candidates, intent, {}) if candidate.course.id not in excluded and candidate.path_role != ROLE_OUT_OF_DOMAIN]
    if reason == "TOO_ADVANCED":
        ranked.sort(key=lambda candidate: (DIFFICULTY.get(candidate.course.difficulty, 1), -candidate.path_score, candidate.course.title.casefold()))
    elif reason == "TOO_EXPENSIVE":
        ranked.sort(key=lambda candidate: (candidate.course.price, -candidate.path_score, candidate.course.title.casefold()))
    else:
        ranked.sort(key=lambda candidate: (-candidate.path_score, DIFFICULTY.get(candidate.course.difficulty, 1), candidate.course.title.casefold()))
    if not ranked:
        return False
    course = ranked[0].course
    item.course_id = course.id
    item.course = course
    item.reason = _fallback_reason(course, intent.primary_domain_label)
    item.how_it_prepares_next = "This replacement preserves the grounded domain policy for the surrounding roadmap."
    item.skills_gained_json = list((course.what_you_will_learn or course.tags or [])[:5])
    item.estimated_hours = _hours(course)
    item.price_snapshot = course.price
    item.currency = course.currency
    path.total_price = sum((Decimal(str(path_item.price_snapshot)) for path_item in path.items), Decimal("0.00"))
    path.estimated_total_hours = sum(_hours(path_item.course) for path_item in path.items if path_item.course)
    path.estimated_weeks = math.ceil(path.estimated_total_hours / path.weekly_hours)
    await db.flush()
    return True
