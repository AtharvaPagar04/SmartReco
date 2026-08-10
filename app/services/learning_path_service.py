from __future__ import annotations

import math
from dataclasses import dataclass
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
from app.services.learning_path_policy import (
    MAX_PATH_COURSES,
    MIN_PATH_COURSES,
    RELATED_DOMAIN_THRESHOLD,
    ROLE_OUT_OF_DOMAIN,
    get_related_domain_score,
)
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


@dataclass
class ReplacementResult:
    replaced: bool
    reason_code: str
    user_message: str
    source: str  # "EXACT_DOMAIN", "RELATED_DOMAIN", or "NONE"
    replacement_course_id: str | None = None
    replacement_course_title: str | None = None
    previous_course_title: str | None = None


def build_replacement_message(
    reason_code: str,
    source: str,
    domain_label: str,
    previous_title: str | None = None,
    replacement_title: str | None = None,
) -> str:
    if source == "EXACT_DOMAIN" and replacement_title and previous_title:
        return f"'{previous_title}' was replaced with '{replacement_title}'."
    if source == "RELATED_DOMAIN" and replacement_title:
        return f"No unused exact {domain_label} match was available, so SmartReco selected a closely related alternative: '{replacement_title}'."

    messages = {
        "ALL_MATCHES_ALREADY_IN_PATH": f"All strong {domain_label} matches are already in this roadmap, so there is no unused exact replacement.",
        "NO_EASIER_CANDIDATE": "No easier grounded replacement is available for this stage.",
        "NO_CHEAPER_CANDIDATE": "No cheaper grounded replacement is available for this stage.",
        "NO_RELATED_CANDIDATE": "No suitable related course is available without adding an unrelated course.",
        "NO_GROUNDED_REPLACEMENT": "No grounded replacement is available right now.",
        "VALIDATION_FAILED": "SmartReco found an alternative, but replacing this stage would make the roadmap invalid.",
        "PERSISTENCE_FAILED": "We found a replacement but could not save it. Please try again.",
    }
    return messages.get(reason_code, "No grounded replacement is available right now.")



def _hours(course: Course) -> int:
    return max(1, math.ceil(course.total_curriculum_minutes / 60))


def _profile_for_input(path_input: LearningPathInput, profile: dict) -> dict:
    """Build compatibility context without turning known skills into targets."""
    intent = LearningPathIntent.from_input(path_input)
    domains = [DOMAIN_BY_CODE[path_input.primary_domain], *(DOMAIN_BY_CODE[code] for code in path_input.secondary_domains)]
    merged = dict(profile)
    merged["top_categories"] = [{"name": category} for domain in domains for category in domain.categories] + profile.get("top_categories", [])[:3]
    merged["top_tags"] = [{"name": tag} for domain in domains for tag in domain.tags] + profile.get("top_tags", [])[:5]
    merged["top_search_terms"] = [{"term": value} for value in intent.goal_labels] + profile.get("top_search_terms", [])[:3]
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


import uuid


async def candidate_courses(
    db: AsyncSession,
    user: User,
    path_input: LearningPathInput,
    excluded: set[str] | None = None,
    trace_context: LearningPathTraceContext | None = None,
) -> tuple[list[RecommendationCandidate], str | None, dict]:
    profile_row = await build_or_refresh_profile(db, user.id)
    profile = _profile_for_input(path_input, profile_row.profile_json or {})
    intent = LearningPathIntent.from_input(path_input)
    limit = max(settings.learning_path_max_candidates, intent.requested_course_count * 3)
    candidates, semantic_used, sql_used, queries = await retrieve_learning_path_candidates(
        db, intent, profile, limit=limit, excluded=excluded, trace_context=trace_context
    )
    return candidates, profile_row.profile_hash, {
        "semantic_retrieval_used": semantic_used,
        "sql_fallback_used": sql_used,
        "retrieval_queries": queries,
        "candidate_limit": limit,
    }


import logging
import time

from app.services.learning_path_logging import LearningPathTraceContext, log_learning_path_step
from app.services.learning_path_policy import ROLE_CROSS_DOMAIN, ROLE_PRIMARY, ROLE_SECONDARY, ROLE_SUPPORTING, classify_course_for_path

logger = logging.getLogger(__name__)


async def _reload_selected_courses(db: AsyncSession, plan: PlanGenerationResult, *, trace_context: LearningPathTraceContext | None = None) -> list[tuple[object, Course]]:
    trace_id = trace_context.trace_id if trace_context else "no_trace"
    t_rel = time.perf_counter()
    ids = [stage.course_id for stage in plan.plan.stages]
    rows = list((await db.scalars(select(Course).where(Course.id.in_(ids), Course.is_active.is_(True)))).all()) if ids else []
    courses = {course.id: course for course in rows}
    rel_dur = (time.perf_counter() - t_rel) * 1000

    requested_count = len(ids)
    loaded_count = len(rows)
    missing_count = requested_count - loaded_count

    log_learning_path_step(
        logger,
        "learning_path.step.success",
        trace_id,
        step="persistence.course_reload",
        duration_ms=rel_dur,
        requested_ids_count=requested_count,
        loaded_courses_count=loaded_count,
        missing_ids_count=missing_count,
    )
    if missing_count > 0:
        missing_ids = list(set(ids) - set(courses.keys()))
        log_learning_path_step(
            logger,
            "learning_path.step.warning",
            trace_id,
            step="persistence.course_reload",
            missing_course_ids=missing_ids,
        )
        if trace_context:
            trace_context.record_failure("persistence.course_reload", "MISSING_COURSES")

    return [(stage, courses[stage.course_id]) for stage in plan.plan.stages if stage.course_id in courses]


async def create_learning_path(db: AsyncSession, user: User, path_input: LearningPathInput, *, status: str = "READY", trace_context: LearningPathTraceContext | None = None) -> LearningPath:
    if trace_context is None:
        trace_context = LearningPathTraceContext()
    trace_id = trace_context.trace_id

    t_intent = time.perf_counter()
    intent = LearningPathIntent.from_input(path_input)
    intent_dur = (time.perf_counter() - t_intent) * 1000

    log_learning_path_step(
        logger,
        "learning_path.step.success",
        trace_id,
        step="intent.build",
        duration_ms=intent_dur,
        primary_domain_code=intent.primary_domain_code,
        secondary_domain_codes=list(intent.secondary_domain_codes),
        goal_codes=list(intent.goal_codes),
        level_code=intent.level_code,
        path_length=intent.path_length,
        requested_course_count=intent.requested_course_count,
        auto_mode=intent.path_length == "AUTO",
    )

    t_prof = time.perf_counter()
    profile_row = await build_or_refresh_profile(db, user.id)
    profile = _profile_for_input(path_input, profile_row.profile_json or {})
    prof_dur = (time.perf_counter() - t_prof) * 1000

    log_learning_path_step(
        logger,
        "learning_path.step.success",
        trace_id,
        step="profile.load",
        duration_ms=prof_dur,
        top_category_count=len(profile.get("top_categories", [])),
        top_tag_count=len(profile.get("top_tags", [])),
        top_search_term_count=len(profile.get("top_search_terms", [])),
        profile_available=bool(profile_row.profile_json),
    )

    limit = max(settings.learning_path_max_candidates, intent.requested_course_count * 3)

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
                t_ret = time.perf_counter()
                candidates, semantic_used, sql_used, queries = await retrieve_learning_path_candidates(db, intent, profile, limit=limit, trace_context=trace_context)
                trace_context.retrieval_duration_ms = int((time.perf_counter() - t_ret) * 1000)

                t_plan = time.perf_counter()
                plan_result = await generate_plan_with_repairs(intent, candidates, profile, trace_context=trace_context)
                trace_context.planner_duration_ms = int((time.perf_counter() - t_plan) * 1000)
        else:
            t_ret = time.perf_counter()
            candidates, semantic_used, sql_used, queries = await retrieve_learning_path_candidates(db, intent, profile, limit=limit, trace_context=trace_context)
            trace_context.retrieval_duration_ms = int((time.perf_counter() - t_ret) * 1000)

            t_plan = time.perf_counter()
            plan_result = await generate_plan_with_repairs(intent, candidates, profile, trace_context=trace_context)
            trace_context.planner_duration_ms = int((time.perf_counter() - t_plan) * 1000)
    else:
        t_ret = time.perf_counter()
        candidates, semantic_used, sql_used, queries = await retrieve_learning_path_candidates(db, intent, profile, limit=limit, trace_context=trace_context)
        trace_context.retrieval_duration_ms = int((time.perf_counter() - t_ret) * 1000)

        t_plan = time.perf_counter()
        plan_result = await generate_plan_with_repairs(intent, candidates, profile, trace_context=trace_context)
        trace_context.planner_duration_ms = int((time.perf_counter() - t_plan) * 1000)

    selected = await _reload_selected_courses(db, plan_result, trace_context=trace_context)
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

    final_source = "MESH" if (plan_result.llm_generation_used and plan_result.repair_count == 0) else ("MESH_REPAIRED" if plan_result.llm_generation_used else ("FALLBACK" if plan_result.deterministic_fallback_used else "NONE"))
    log_learning_path_step(
        logger,
        "learning_path.step.success",
        trace_id,
        step="plan.finalize",
        final_source=final_source,
        selected_count=len(courses),
        effective_target_count=effective_count,
        final_validation_status=plan_result.validation_status,
        llm_generation_used=plan_result.llm_generation_used,
        deterministic_fallback_used=plan_result.deterministic_fallback_used,
    )

    sel_roles = {ROLE_PRIMARY: 0, ROLE_SECONDARY: 0, ROLE_CROSS_DOMAIN: 0, ROLE_SUPPORTING: 0}
    for course in courses:
        r, _ = classify_course_for_path(course, intent.primary_domain_code, intent.secondary_domain_codes)
        if r in sel_roles:
            sel_roles[r] += 1

    trace_context.selected_primary_count = sel_roles[ROLE_PRIMARY]
    trace_context.selected_secondary_count = sel_roles[ROLE_SECONDARY]
    trace_context.selected_cross_domain_count = sel_roles[ROLE_CROSS_DOMAIN]
    trace_context.selected_supporting_count = sel_roles[ROLE_SUPPORTING]
    trace_context.total_duration_ms = trace_context.elapsed_ms()

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
        "pipeline_first_failure_stage": trace_context.first_failure_stage,
        "pipeline_first_failure_reason": trace_context.first_failure_reason,
        "pipeline_final_failure_stage": trace_context.final_failure_stage,
        "pipeline_final_failure_reason": trace_context.final_failure_reason,
        "selected_primary_count": trace_context.selected_primary_count,
        "selected_secondary_count": trace_context.selected_secondary_count,
        "selected_cross_domain_count": trace_context.selected_cross_domain_count,
        "selected_supporting_count": trace_context.selected_supporting_count,
        "schema_validation_errors": list(plan_result.schema_validation_errors),
        "validation_violations": list(plan_result.violations),
        "mesh_attempt_count": trace_context.mesh_attempt_count,
        "mesh_attempt_durations_ms": list(trace_context.mesh_attempt_durations_ms),
        "retrieval_duration_ms": trace_context.retrieval_duration_ms,
        "planner_duration_ms": trace_context.planner_duration_ms,
        "total_generation_duration_ms": trace_context.total_duration_ms,
        "path_mode": intent.path_length,
        "auto_min": MIN_PATH_COURSES if intent.path_length == "AUTO" else None,
        "auto_max": MAX_PATH_COURSES if intent.path_length == "AUTO" else None,
        "requested_count": requested_count,
        "selected_domain_count": len(intent.secondary_domain_codes) + 1,
        "selected_domains": [intent.primary_domain_code, *intent.secondary_domain_codes],
        "eligible_course_count": available_safe_count,
        "effective_target_count": effective_count,
        "selected_count": len(courses) if is_valid else 0,
        "coverage_limited": coverage_limited,
        "covered_domains": list(coverage.covered_domains) if coverage else [],
        "uncovered_domains": list(coverage.uncovered_domains) if coverage else [],
        "domain_coverage_limited": coverage.domain_coverage_limited if coverage else False,
        "coverage_reason": coverage_reason,
        "coverage_status": "INSUFFICIENT" if available_safe_count < MIN_PATH_COURSES else ("LIMITED" if coverage_limited else "SUFFICIENT"),
        "explanation_source": "MESH" if plan_result.llm_generation_used else "FALLBACK",
        "failure_reason": None if is_valid else (plan_result.validation_status if plan_result.validation_status != "INSUFFICIENT_COVERAGE" else "INSUFFICIENT_CATALOG_COVERAGE"),
    }

    t_lp = time.perf_counter()
    log_learning_path_step(
        logger,
        "learning_path.step.start",
        trace_id,
        step="persistence.learning_path",
    )
    path = LearningPath(
        user_id=user.id,
        title=plan_result.plan.title,
        summary=f"{plan_result.plan.summary} {plan_result.plan.final_outcome}".strip(),
        status=final_status,
        primary_domain=path_input.primary_domain,
        secondary_domains_json=path_input.secondary_domains,
        goal_code=path_input.goal,
        level_code=path_input.level,
        weekly_hours=path_input.weekly_hours,
        target_weeks=path_input.target_weeks,
        budget_type=path_input.budget_type,
        budget_scope=path_input.budget_scope,
        budget_amount=path_input.effective_budget(),
        currency=path_input.currency,
        path_length_preference=path_input.path_length,
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
    lp_dur = (time.perf_counter() - t_lp) * 1000
    log_learning_path_step(
        logger,
        "learning_path.step.success",
        trace_id,
        step="persistence.learning_path",
        duration_ms=lp_dur,
        path_id=path.id,
        status=final_status,
    )

    t_item = time.perf_counter()
    created_items = 0
    expected_items = len(courses) if is_valid else 0
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
            created_items += 1

    item_dur = (time.perf_counter() - t_item) * 1000
    log_learning_path_step(
        logger,
        "learning_path.step.success",
        trace_id,
        step="persistence.items",
        duration_ms=item_dur,
        expected_count=expected_items,
        created_count=created_items,
    )
    if created_items != expected_items:
        log_learning_path_step(
            logger,
            "learning_path.step.error",
            trace_id,
            step="persistence.items",
            error="ITEM_COUNT_MISMATCH",
            expected_count=expected_items,
            created_count=created_items,
        )
        trace_context.record_failure("persistence.items", "ITEM_COUNT_MISMATCH")

    t_run = time.perf_counter()
    run = LearningPathGenerationRun(
        learning_path_id=path.id,
        status="SUCCEEDED" if is_valid else "FAILED",
        candidate_count=len(candidates),
        selected_count=len(courses),
        used_fallback=sql_used or plan_result.deterministic_fallback_used,
        metadata_json=metadata,
        started_at=now,
        completed_at=now,
    )
    db.add(run)
    await db.flush()
    run_dur = (time.perf_counter() - t_run) * 1000
    log_learning_path_step(
        logger,
        "learning_path.step.success",
        trace_id,
        step="persistence.generation_run",
        duration_ms=run_dur,
        generation_run_id=run.id,
        metadata_key_count=len(metadata),
        validation_status=plan_result.validation_status,
        llm_generation_used=plan_result.llm_generation_used,
        deterministic_fallback_used=plan_result.deterministic_fallback_used,
        selected_count=len(courses),
    )

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



async def replace_item(
    db: AsyncSession,
    path: LearningPath,
    item: LearningPathItem,
    reason: str,
    trace_id: str | None = None,
) -> ReplacementResult:
    t0 = time.perf_counter()
    active_trace_id = trace_id or str(uuid.uuid4())
    trace_ctx = LearningPathTraceContext(trace_id=active_trace_id)
    current_course_id = item.course_id
    current_course_title = item.course.title if item.course else None

    domain_option = DOMAIN_BY_CODE.get(path.primary_domain.upper()) if path.primary_domain else None
    domain_label = domain_option.label if domain_option else (path.primary_domain or "domain")

    log_learning_path_step(
        logger,
        "learning_path.replace.request.start",
        active_trace_id,
        path_id=path.id,
        item_id=item.id,
        current_course_id=current_course_id,
        current_course_title=current_course_title,
        requested_difficulty=reason,
        position=item.position,
    )

    log_learning_path_step(
        logger,
        "learning_path.replace.step.start",
        active_trace_id,
        step="lookup",
        path_found=True,
        item_found=True,
        item_position=item.position,
        current_course_id=current_course_id,
    )

    path_input = LearningPathInput.model_validate(path.input_json)
    user = await db.scalar(select(User).where(User.id == path.user_id))
    if not user:
        log_learning_path_step(
            logger,
            "learning_path.replace.step.error",
            active_trace_id,
            step="lookup",
            error_reason="USER_NOT_FOUND",
        )
        msg = build_replacement_message("VALIDATION_FAILED", "NONE", domain_label, current_course_title)
        return ReplacementResult(False, "VALIDATION_FAILED", msg, "NONE", previous_course_title=current_course_title)

    excluded_existing = {path_item.course_id for path_item in path.items}
    selected_domains = [path.primary_domain, *(path.secondary_domains_json or [])]

    log_learning_path_step(
        logger,
        "learning_path.replace.step.start",
        active_trace_id,
        step="constraints",
        selected_domains=selected_domains,
        goal_codes=[path.goal_code],
        current_level=path.level_code,
        requested_difficulty=reason,
        current_stage_position=item.position,
        existing_course_ids=list(excluded_existing),
        excluded_current_course_id=current_course_id,
    )

    candidates, _, _ = await candidate_courses(db, user, path_input, excluded=excluded_existing, trace_context=trace_ctx)
    candidate_count_before_exclusions = len(candidates)
    non_excluded_candidates = [c for c in candidates if c.course.id not in excluded_existing]
    excluded_existing_count = candidate_count_before_exclusions - len(non_excluded_candidates)

    intent = LearningPathIntent.from_input(path_input)
    preranked = pre_rank_candidates(non_excluded_candidates, intent, {})

    # Tier 1: Exact Domain Evaluation
    log_learning_path_step(
        logger,
        "learning_path.replace.step.start",
        active_trace_id,
        step="candidate_exact",
        selected_domains=selected_domains,
    )

    exact_candidates = [c for c in preranked if c.path_role != ROLE_OUT_OF_DOMAIN]
    current_diff = DIFFICULTY.get(item.course.difficulty if item.course else "", 1)
    current_price = item.price_snapshot if item.price_snapshot is not None else (item.course.price if item.course else Decimal("0.00"))

    if reason == "TOO_ADVANCED":
        filtered_exact = [c for c in exact_candidates if DIFFICULTY.get(c.course.difficulty, 1) < current_diff]
        sort_key_exact = lambda c: (DIFFICULTY.get(c.course.difficulty, 1), -c.path_score, c.course.title.casefold())
    elif reason == "TOO_BASIC":
        filtered_exact = [c for c in exact_candidates if DIFFICULTY.get(c.course.difficulty, 1) >= current_diff]
        sort_key_exact = lambda c: (-DIFFICULTY.get(c.course.difficulty, 1), -c.path_score, c.course.title.casefold())
    elif reason == "TOO_EXPENSIVE":
        filtered_exact = [c for c in exact_candidates if c.course.price < current_price]
        sort_key_exact = lambda c: (c.course.price, -c.path_score, c.course.title.casefold())
    else:
        filtered_exact = exact_candidates
        sort_key_exact = lambda c: (-c.path_score, DIFFICULTY.get(c.course.difficulty, 1), c.course.title.casefold())

    ranked_exact = sorted(filtered_exact, key=sort_key_exact)

    chosen_candidate: RecommendationCandidate | None = None
    source = "NONE"
    related_candidate_count_after_domain_filter = 0
    filtered_exact_count = len(filtered_exact)

    if ranked_exact:
        chosen_candidate = ranked_exact[0]
        source = "EXACT_DOMAIN"
        log_learning_path_step(
            logger,
            "learning_path.replace.step.success",
            active_trace_id,
            step="candidate_exact",
            candidate_count=len(ranked_exact),
            chosen_course_id=chosen_candidate.course.id,
            chosen_course_title=chosen_candidate.course.title,
        )
    else:
        log_learning_path_step(
            logger,
            "learning_path.replace.step.warning",
            active_trace_id,
            step="candidate_exact",
            reason="NO_EXACT_MATCH",
            exact_candidate_count=len(exact_candidates),
            filtered_exact_count=0,
        )

        # Tier 2: Related Domain Fallback Evaluation
        log_learning_path_step(
            logger,
            "learning_path.replace.step.start",
            active_trace_id,
            step="candidate_related",
            selected_domains=selected_domains,
        )

        related_eval: list[tuple[RecommendationCandidate, float, str]] = []
        for c in non_excluded_candidates:
            rel_score, rel_dom = get_related_domain_score(c.course, selected_domains)
            if rel_score >= RELATED_DOMAIN_THRESHOLD and rel_dom:
                related_eval.append((c, rel_score, rel_dom))

        related_candidate_count_before_filter = len(non_excluded_candidates)
        related_candidate_count_after_domain_filter = len(related_eval)

        if reason == "TOO_ADVANCED":
            filtered_related = [t for t in related_eval if DIFFICULTY.get(t[0].course.difficulty, 1) < current_diff]
            sort_key_rel = lambda t: (DIFFICULTY.get(t[0].course.difficulty, 1), -t[1], t[0].course.title.casefold())
        elif reason == "TOO_BASIC":
            filtered_related = [t for t in related_eval if DIFFICULTY.get(t[0].course.difficulty, 1) >= current_diff]
            sort_key_rel = lambda t: (-DIFFICULTY.get(t[0].course.difficulty, 1), -t[1], t[0].course.title.casefold())
        elif reason == "TOO_EXPENSIVE":
            filtered_related = [t for t in related_eval if t[0].course.price < current_price]
            sort_key_rel = lambda t: (t[0].course.price, -t[1], t[0].course.title.casefold())
        else:
            filtered_related = related_eval
            sort_key_rel = lambda t: (-t[1], DIFFICULTY.get(t[0].course.difficulty, 1), t[0].course.title.casefold())

        related_candidate_count_after_reason_filter = len(filtered_related)
        ranked_related = sorted(filtered_related, key=sort_key_rel)
        final_related_candidate_count = len(ranked_related)

        if ranked_related:
            chosen_tuple = ranked_related[0]
            chosen_candidate = chosen_tuple[0]
            source = "RELATED_DOMAIN"
            log_learning_path_step(
                logger,
                "learning_path.replace.step.success",
                active_trace_id,
                step="candidate_related",
                related_candidate_count_before_filter=related_candidate_count_before_filter,
                related_candidate_count_after_domain_filter=related_candidate_count_after_domain_filter,
                related_candidate_count_after_reason_filter=related_candidate_count_after_reason_filter,
                final_related_candidate_count=final_related_candidate_count,
                replacement_source="RELATED_DOMAIN",
                chosen_course_id=chosen_candidate.course.id,
                chosen_course_title=chosen_candidate.course.title,
                related_domain=chosen_tuple[2],
                related_affinity_score=chosen_tuple[1],
            )

    if not chosen_candidate:
        all_catalog_exact_matches_in_path = False
        if exact_candidates and len(exact_candidates) == len([c for c in preranked if c.path_role != ROLE_OUT_OF_DOMAIN and c.course.id in excluded_existing]):
            all_catalog_exact_matches_in_path = True

        if reason == "TOO_ADVANCED":
            reason_code = "NO_EASIER_CANDIDATE"
        elif reason == "TOO_EXPENSIVE":
            reason_code = "NO_CHEAPER_CANDIDATE"
        elif all_catalog_exact_matches_in_path:
            reason_code = "ALL_MATCHES_ALREADY_IN_PATH"
        elif related_candidate_count_after_domain_filter > 0:
            reason_code = "NO_RELATED_CANDIDATE"
        else:
            reason_code = "NO_GROUNDED_REPLACEMENT"

        log_learning_path_step(
            logger,
            "learning_path.replace.step.warning",
            active_trace_id,
            step="candidate_selection",
            reason=reason_code,
            current_course_id=current_course_id,
            current_course_title=current_course_title,
            selected_domains=selected_domains,
            requested_difficulty=reason,
            existing_roadmap_count=len(path.items),
            exact_candidate_count=len(exact_candidates),
            related_candidate_count=related_candidate_count_after_domain_filter,
            excluded_existing_count=excluded_existing_count,
            difficulty_filtered_count=filtered_exact_count,
            final_candidate_count=0,
            failure_reason_code=reason_code,
        )
        log_learning_path_step(
            logger,
            "learning_path.replace.request.failed",
            active_trace_id,
            path_id=path.id,
            item_id=item.id,
            reason=reason_code,
        )
        msg = build_replacement_message(reason_code, "NONE", domain_label, current_course_title)
        return ReplacementResult(False, reason_code, msg, "NONE", previous_course_title=current_course_title)

    course = chosen_candidate.course
    other_course_ids = {pi.course_id for pi in path.items if pi.id != item.id}
    if not course.is_active or course.id in other_course_ids:
        log_learning_path_step(
            logger,
            "learning_path.replace.step.error",
            active_trace_id,
            step="validation",
            reason="REPLACEMENT_VALIDATION_FAILED",
            replacement_course_id=course.id,
            is_active=course.is_active,
            is_duplicate=(course.id in other_course_ids),
        )
        log_learning_path_step(
            logger,
            "learning_path.replace.request.failed",
            active_trace_id,
            path_id=path.id,
            item_id=item.id,
            reason="VALIDATION_FAILED",
        )
        msg = build_replacement_message("VALIDATION_FAILED", "NONE", domain_label, current_course_title)
        return ReplacementResult(False, "VALIDATION_FAILED", msg, "NONE", previous_course_title=current_course_title)

    log_learning_path_step(
        logger,
        "learning_path.replace.step.success",
        active_trace_id,
        step="validation",
        replacement_course_id=course.id,
        replacement_course_title=course.title,
    )

    item.course_id = course.id
    item.course = course
    item.reason = _fallback_reason(course, intent.primary_domain_label)
    item.skills_gained_json = list((course.what_you_will_learn or course.tags or [])[:5])
    item.estimated_hours = _hours(course)
    item.price_snapshot = course.price
    item.currency = course.currency

    sorted_items = sorted(path.items, key=lambda x: x.position)
    idx = next((i for i, x in enumerate(sorted_items) if x.id == item.id), -1)
    if idx != -1:
        if idx + 1 < len(sorted_items):
            following = sorted_items[idx + 1].course
            item.how_it_prepares_next = f"This stage prepares you for {following.title}."
        else:
            item.how_it_prepares_next = f"This stage advances the {intent.primary_domain_label} outcome."

        if idx > 0:
            previous_item = sorted_items[idx - 1]
            previous_item.how_it_prepares_next = f"This stage prepares you for {course.title}."

    path.total_price = sum((Decimal(str(path_item.price_snapshot)) for path_item in path.items), Decimal("0.00"))
    path.estimated_total_hours = sum(_hours(path_item.course) for path_item in path.items if path_item.course)
    path.estimated_weeks = math.ceil(path.estimated_total_hours / path.weekly_hours)

    log_learning_path_step(
        logger,
        "learning_path.replace.step.start",
        active_trace_id,
        step="persistence.update_item",
        path_id=path.id,
        item_id=item.id,
        replacement_course_id=course.id,
    )
    await db.flush()
    dur_ms = (time.perf_counter() - t0) * 1000

    log_learning_path_step(
        logger,
        "learning_path.replace.step.success",
        active_trace_id,
        step="persistence.update_item",
        duration_ms=dur_ms,
        path_id=path.id,
        item_id=item.id,
        replacement_course_id=course.id,
        replacement_course_title=course.title,
    )
    log_learning_path_step(
        logger,
        "learning_path.replace.request.success",
        active_trace_id,
        duration_ms=dur_ms,
        path_id=path.id,
        item_id=item.id,
        replacement_course_id=course.id,
        replacement_source=source,
    )

    reason_code = "REPLACED_EXACT" if source == "EXACT_DOMAIN" else "REPLACED_RELATED"
    msg = build_replacement_message(reason_code, source, domain_label, current_course_title, course.title)
    return ReplacementResult(
        replaced=True,
        reason_code=reason_code,
        user_message=msg,
        source=source,
        replacement_course_id=course.id,
        replacement_course_title=course.title,
        previous_course_title=current_course_title,
    )
