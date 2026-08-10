import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import settings
from app.models import Course
from app.services.learning_path_intent import LearningPathIntent
from app.services.learning_path_policy import (
    DOMAIN_SCORE_WEIGHTS,
    ROLE_CROSS_DOMAIN,
    ROLE_OUT_OF_DOMAIN,
    ROLE_PRIMARY,
    ROLE_SECONDARY,
    ROLE_SUPPORTING,
    LearningPathCoverage,
    classify_course_for_path,
    resolve_learning_path_coverage,
)
from app.services.learning_path_validator import validate_learning_path_plan
from app.services.mesh_chat_service import MeshChatError, generate_learning_path_json
from app.services.mesh_client import MeshConfigurationError
from app.services.learning_path_logging import LearningPathTraceContext, log_learning_path_step
from app.services.recommendation_retrieval_service import RecommendationCandidate

logger = logging.getLogger(__name__)


class LearningPathPlanStage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    position: int = Field(ge=1, le=8)
    course_id: str = Field(min_length=1)
    role: str = "PRIMARY"
    goal_codes: list[str] = Field(default_factory=list)
    why_this_course: str = ""
    goal_alignment: str = ""
    skill_gain: str = ""
    how_it_leads_forward: str = ""


class LearningPathPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=2000)
    final_outcome: str = Field(min_length=1, max_length=1000)
    stages: list[LearningPathPlanStage] = Field(min_length=0, max_length=8)


@dataclass(frozen=True)
class PlanGenerationResult:
    plan: LearningPathPlan
    llm_generation_used: bool
    repair_count: int
    deterministic_fallback_used: bool
    validation_status: str
    violations: tuple[dict, ...] = ()
    coverage: LearningPathCoverage | None = None
    llm_attempted: bool = False
    llm_failure_reason: str | None = None
    prompt_candidate_count: int = 0
    schema_validation_errors: tuple[dict, ...] = ()


TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.-]*", re.I)
DIFFICULTY = {"BEGINNER": 0, "INTERMEDIATE": 1, "ADVANCED": 2}


def _classify_exception(exc: Exception) -> str:
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return "MESH_TIMEOUT"
    if isinstance(exc, ValidationError):
        return "MESH_SCHEMA_VALIDATION_ERROR"
    if isinstance(exc, MeshConfigurationError):
        return "MESH_CONFIGURATION_ERROR"
    if isinstance(exc, MeshChatError):
        if exc.code in ("mesh_provider_timeout", "mesh_timeout"):
            return "MESH_TIMEOUT"
        if exc.code in ("mesh_empty_response", "mesh_invalid_response", "mesh_invalid_json"):
            return "MESH_SCHEMA_VALIDATION_ERROR"
        if exc.code == "mesh_connection_failed":
            return "MESH_CONNECTION_FAILED"
        if exc.code in ("mesh_status_error", "mesh_retryable_status"):
            return "MESH_PROVIDER_ERROR"
        return f"MESH_{exc.code.upper()}"
    if isinstance(exc, json.JSONDecodeError):
        return "MESH_SCHEMA_VALIDATION_ERROR"
    return "MESH_PLANNER_ERROR"


def _sanitize_log_message(msg: str) -> str:
    if not msg:
        return ""
    msg = re.sub(r"(?i)(api[-_]?key|authorization|bearer|secret|token)[:=]\s*[^\s,;]+", r"\1=[REDACTED]", msg)
    msg = re.sub(r"sk-[a-zA-Z0-9]{20,}", "[REDACTED_KEY]", msg)
    return msg[:300]


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in TOKEN_RE.findall(value or "") if len(token) > 1}


def _course_text(course: Course) -> str:
    values = [course.title, course.category, *(course.tags or []), *(course.what_you_will_learn or []), course.short_description, course.description, *(course.prerequisites or [])]
    if isinstance(course.final_project, dict):
        values.extend(str(value) for value in course.final_project.values())
    return " ".join(str(value) for value in values if value)


def _goal_fit(course: Course, intent: LearningPathIntent) -> float:
    text = _tokens(_course_text(course))
    scores = []
    for goal in intent.goal_labels:
        wanted = _tokens(goal)
        scores.append(len(text & wanted) / max(1, len(wanted)))
    return min(1.0, max(scores, default=0.0) + (0.25 if "PRODUCTION" in intent.goal_codes and course.final_project else 0.0))


def _level_fit(course: Course, intent: LearningPathIntent) -> float:
    learner_level = {"BEGINNER": 0, "FAMILIAR": 0, "FOUNDATIONS": 1, "INTERMEDIATE": 1, "ADVANCED": 2}[intent.level_code]
    distance = abs(DIFFICULTY.get(course.difficulty, 1) - learner_level)
    return max(0.0, 1.0 - 0.35 * distance)


def pre_rank_candidates(
    candidates: list[RecommendationCandidate],
    intent: LearningPathIntent,
    profile: dict,
    *,
    trace_context: LearningPathTraceContext | None = None,
) -> list[RecommendationCandidate]:
    trace_id = trace_context.trace_id if trace_context else "no_trace"
    t0 = time.perf_counter()
    for candidate in candidates:
        role, affinities = classify_course_for_path(candidate.course, intent.primary_domain_code, intent.secondary_domain_codes)
        primary = affinities[intent.primary_domain_code].score
        secondary = max((affinities[code].score for code in intent.secondary_domain_codes), default=0.0)
        domain = 0.65 * primary + 0.35 * secondary
        goal = _goal_fit(candidate.course, intent)
        level = _level_fit(candidate.course, intent)
        behavior = 0.0
        if profile.get("top_categories") and candidate.course.category.casefold() == str(profile["top_categories"][0].get("name", "")).casefold():
            behavior = 1.0
        semantic = max(0.0, min(1.0, float(candidate.semantic_score or 0.0)))
        candidate.path_role = role
        candidate.primary_affinity = primary
        candidate.secondary_affinity = secondary
        candidate.goal_affinity = goal
        candidate.level_fit = level
        candidate.path_score = round(
            DOMAIN_SCORE_WEIGHTS["semantic"] * semantic
            + DOMAIN_SCORE_WEIGHTS["domain"] * domain
            + DOMAIN_SCORE_WEIGHTS["goals"] * goal
            + DOMAIN_SCORE_WEIGHTS["level"] * level
            + DOMAIN_SCORE_WEIGHTS["behavior"] * behavior,
            6,
        )
        candidate.evidence["learning_path"] = {
            "role": role,
            "primary_affinity": primary,
            "secondary_affinity": secondary,
            "goal_affinity": goal,
            "level_fit": level,
            "path_score": candidate.path_score,
        }

    sorted_candidates = sorted(candidates, key=lambda item: (-item.path_score, -(item.semantic_score or 0.0), item.course.title.casefold(), item.course.id))
    dur_ms = (time.perf_counter() - t0) * 1000

    role_counts = {ROLE_PRIMARY: 0, ROLE_SECONDARY: 0, ROLE_CROSS_DOMAIN: 0, ROLE_SUPPORTING: 0, ROLE_OUT_OF_DOMAIN: 0}
    for item in sorted_candidates:
        if item.path_role in role_counts:
            role_counts[item.path_role] += 1

    log_learning_path_step(
        logger,
        "learning_path.step.success",
        trace_id,
        step="candidates.prerank",
        duration_ms=dur_ms,
        candidate_count=len(sorted_candidates),
        primary_count=role_counts[ROLE_PRIMARY],
        secondary_count=role_counts[ROLE_SECONDARY],
        cross_domain_count=role_counts[ROLE_CROSS_DOMAIN],
        supporting_count=role_counts[ROLE_SUPPORTING],
        out_of_domain_count=role_counts[ROLE_OUT_OF_DOMAIN],
    )

    for item in sorted_candidates[:10]:
        log_learning_path_step(
            logger,
            "learning_path.step.debug",
            trace_id,
            step="candidates.prerank_top",
            course_id=item.course.id,
            title=item.course.title,
            role=item.path_role,
            path_score=item.path_score,
            semantic_score=item.semantic_score,
            primary_affinity=item.primary_affinity,
            secondary_affinity=item.secondary_affinity,
        )

    return sorted_candidates


def _candidate_payload(candidate: RecommendationCandidate) -> dict:
    course = candidate.course
    path_meta = candidate.evidence.get("learning_path", {})
    final_project = course.final_project if isinstance(course.final_project, dict) else None
    return {
        "course_id": course.id,
        "title": course.title,
        "category": course.category,
        "tags": list(course.tags or [])[:10],
        "difficulty": course.difficulty,
        "estimated_hours": max(1, round(course.total_curriculum_minutes / 60)),
        "price": float(course.price),
        "currency": course.currency,
        "short_description": course.short_description,
        "what_you_will_learn": list(course.what_you_will_learn or [])[:6],
        "prerequisites": list(course.prerequisites or [])[:5],
        "final_project": {key: final_project.get(key) for key in ("title", "description")} if final_project else None,
        "semantic_score": candidate.semantic_score,
        "retrieval_sources": list(candidate.retrieval_sources),
        "domain_role": candidate.path_role,
        "primary_domain_affinity": candidate.primary_affinity,
        "secondary_domain_affinity": candidate.secondary_affinity,
        "goal_alignment": candidate.goal_affinity,
        "level_fit": candidate.level_fit,
    }


def select_fallback_courses(
    candidates: list[RecommendationCandidate],
    intent: LearningPathIntent,
    profile: dict,
    *,
    target_count: int | None = None,
    excluded_ids: set[str] | None = None,
    trace_context: LearningPathTraceContext | None = None,
) -> list[Course]:
    trace_id = trace_context.trace_id if trace_context else "no_trace"
    ordered = pre_rank_candidates([item for item in candidates if item.course.id not in (excluded_ids or set())], intent, profile, trace_context=trace_context)
    needed_count = target_count if target_count is not None else intent.requested_course_count
    allowed = [item for item in ordered if item.path_role != ROLE_OUT_OF_DOMAIN]
    selected: list[RecommendationCandidate] = []
    budget = Decimal(intent.budget_amount) if intent.budget_type == "CUSTOM" and intent.budget_amount else {"FREE": Decimal("0"), "UNDER_50": Decimal("50"), "UNDER_100": Decimal("100"), "UNDER_200": Decimal("200")}.get(intent.budget_type)
    total = Decimal("0")

    def affordable(item: RecommendationCandidate) -> bool:
        nonlocal total
        price = Decimal(str(item.course.price))
        if intent.budget_type == "FREE" and price:
            return False
        if intent.budget_scope == "COURSE" and budget is not None and price > budget:
            return False
        if intent.budget_scope == "PATH" and budget is not None and total + price > budget:
            return False
        return True

    for item in allowed:
        if len(selected) >= needed_count or item in selected:
            continue
        if not affordable(item):
            log_learning_path_step(
                logger,
                "learning_path.step.debug",
                trace_id,
                step="fallback.skipped_candidate",
                course_id=item.course.id,
                title=item.course.title,
                reason="BUDGET",
            )
            continue
        selected.append(item)
        total += Decimal(str(item.course.price))

    sel_roles = {ROLE_PRIMARY: 0, ROLE_SECONDARY: 0, ROLE_CROSS_DOMAIN: 0, ROLE_SUPPORTING: 0}
    for item in selected:
        if item.path_role in sel_roles:
            sel_roles[item.path_role] += 1

    log_learning_path_step(
        logger,
        "learning_path.step.success",
        trace_id,
        step="fallback.select",
        selected_count=len(selected),
        primary=sel_roles[ROLE_PRIMARY],
        secondary=sel_roles[ROLE_SECONDARY],
        cross_domain=sel_roles[ROLE_CROSS_DOMAIN],
        supporting=sel_roles[ROLE_SUPPORTING],
    )
    for item in selected:
        log_learning_path_step(
            logger,
            "learning_path.step.debug",
            trace_id,
            step="fallback.selected_course",
            course_id=item.course.id,
            title=item.course.title,
            role=item.path_role,
        )

    return [item.course for item in selected]


def fallback_plan(courses: list[Course], intent: LearningPathIntent) -> LearningPathPlan:
    stages = []
    goal_names = ", ".join(intent.goal_labels)
    for position, course in enumerate(courses, 1):
        role, _ = classify_course_for_path(course, intent.primary_domain_code, intent.secondary_domain_codes)
        goal_codes = list(intent.goal_codes) if position == 1 else [intent.goal_codes[min(position - 1, len(intent.goal_codes) - 1)]]
        skills = ", ".join((course.what_you_will_learn or course.tags or [])[:3]) or course.category

        why = f"{course.title} strengthens your {intent.primary_domain_label} roadmap by focusing on {skills}."
        alignment = f"Directly advances your goal to {goal_names.casefold()}."
        if position < len(courses):
            next_course = courses[position]
            leads = f"These core competencies prepare you for the next stage, {next_course.title}."
        else:
            leads = f"This capstone stage solidifies your practical mastery of {intent.primary_domain_label}."

        stages.append(LearningPathPlanStage(
            position=position,
            course_id=course.id,
            role=role,
            goal_codes=goal_codes,
            why_this_course=why,
            goal_alignment=alignment,
            skill_gain=skills,
            how_it_leads_forward=leads,
        ))
    return LearningPathPlan(
        title=f"Your {intent.primary_domain_label} learning path",
        summary=f"A grounded {intent.primary_domain_label} roadmap for {goal_names.lower()}.",
        final_outcome=f"Complete a practical {intent.primary_domain_label} path while applying the selected goals.",
        stages=stages,
    )


async def generate_plan_with_repairs(
    intent: LearningPathIntent,
    candidates: list[RecommendationCandidate],
    profile: dict,
    *,
    trace_context: LearningPathTraceContext | None = None,
) -> PlanGenerationResult:
    trace_id = trace_context.trace_id if trace_context else "no_trace"
    ranked = pre_rank_candidates(candidates, intent, profile, trace_context=trace_context)
    coverage = resolve_learning_path_coverage(ranked, intent)

    log_learning_path_step(
        logger,
        "learning_path.step.success",
        trace_id,
        step="coverage.resolve",
        path_mode=intent.path_length,
        requested_count=coverage.requested_count,
        available_safe_count=coverage.available_safe_count,
        effective_target_count=coverage.effective_target_count,
        coverage_limited=coverage.coverage_limited,
        coverage_reason=coverage.coverage_reason,
        selected_domains=[intent.primary_domain_code, *intent.secondary_domain_codes],
        eligible_course_count=coverage.available_safe_count,
        covered_domains=coverage.covered_domains,
        uncovered_domains=coverage.uncovered_domains,
        domain_coverage_limited=coverage.domain_coverage_limited,
        primary=coverage.primary_available,
        secondary=coverage.secondary_available,
        cross_domain=coverage.cross_domain_available,
        supporting=coverage.supporting_available,
    )
    log_learning_path_step(
        logger,
        "learning_path.step.success",
        trace_id,
        step="domain.coverage",
        covered_domains=coverage.covered_domains,
        uncovered_domains=coverage.uncovered_domains,
        domain_coverage_limited=coverage.domain_coverage_limited,
    )

    if coverage.effective_target_count < 3:
        if trace_context:
            trace_context.record_failure("coverage.resolve", "INSUFFICIENT_COVERAGE")
        empty_plan = LearningPathPlan(
            title=f"Your {intent.primary_domain_label} learning path",
            summary=f"Insufficient aligned catalog coverage for {intent.primary_domain_label}.",
            final_outcome="The catalog does not contain enough aligned courses for a roadmap.",
            stages=[],
        )
        return PlanGenerationResult(
            plan=empty_plan,
            llm_generation_used=False,
            repair_count=0,
            deterministic_fallback_used=False,
            validation_status="INSUFFICIENT_COVERAGE",
            violations=({"code": "INSUFFICIENT_COVERAGE", "message": f"Fewer than {3} aligned eligible courses were found. Eligible courses: {coverage.available_safe_count}."},),
            coverage=coverage,
            llm_attempted=False,
            llm_failure_reason=None,
            prompt_candidate_count=0,
            schema_validation_errors=(),
        )

    safe_candidates = [c for c in ranked if c.path_role != ROLE_OUT_OF_DOMAIN]
    prompt_candidate_list = safe_candidates[:coverage.effective_target_count]
    prompt_candidates = [_candidate_payload(candidate) for candidate in prompt_candidate_list]
    prompt_candidate_count = len(prompt_candidates)

    log_learning_path_step(
        logger,
        "learning_path.step.success",
        trace_id,
        step="planner.prompt_candidates",
        safe_candidate_count=len(safe_candidates),
        prompt_candidate_count=prompt_candidate_count,
        candidate_limit=settings.learning_path_max_candidates,
        effective_target_count=coverage.effective_target_count,
    )
    for c in prompt_candidate_list:
        log_learning_path_step(
            logger,
            "learning_path.step.debug",
            trace_id,
            step="planner.prompt_candidate_item",
            course_id=c.course.id,
            title=c.course.title,
            role=c.path_role,
            difficulty=c.course.difficulty,
        )

    prompt_intent = intent.to_prompt_dict()
    prompt_intent.update(coverage.to_dict())
    prompt_intent["behavioral_context"] = {
        key: profile.get(key, [])
        for key in ("top_categories", "top_tags", "top_search_terms")
        if profile.get(key)
    }

    llm_attempted = False
    llm_failure_reason: str | None = None
    last_plan: dict | None = None
    last_violations: list[dict] = []
    schema_validation_errors: list[dict] = []
    repair_count = 0
    model = settings.learning_path_chat_model or settings.mesh_chat_model
    deadline = asyncio.get_running_loop().time() + settings.mesh_total_budget_seconds

    for attempt in range(settings.learning_path_max_repairs + 1):
        repair = None if attempt == 0 else {"previous_plan": last_plan, "violations": last_violations}
        remaining = deadline - asyncio.get_running_loop().time()
        log_learning_path_step(
            logger,
            "learning_path.step.info",
            trace_id,
            step="planner.mesh_budget",
            remaining_budget_seconds=round(remaining, 2),
        )
        if remaining <= 0:
            if llm_attempted and llm_failure_reason is None:
                llm_failure_reason = "MESH_TIMEOUT"
            log_learning_path_step(
                logger,
                "learning_path.step.error",
                trace_id,
                step="planner.mesh_budget",
                status="error",
                reason="TOTAL_BUDGET_EXHAUSTED",
            )
            if trace_context:
                trace_context.record_failure("planner.mesh_budget", "TOTAL_BUDGET_EXHAUSTED")
            break

        if attempt > 0:
            repair_reason = "SCHEMA" if (llm_failure_reason == "MESH_SCHEMA_VALIDATION_ERROR") else "DETERMINISTIC_VALIDATION"
            log_learning_path_step(
                logger,
                "learning_path.step.start",
                trace_id,
                step="planner.repair",
                repair_number=attempt,
                repair_reason_type=repair_reason,
                violation_codes=[v.get("code") for v in last_violations],
                previous_stage_count=len(last_plan.get("stages", [])) if isinstance(last_plan, dict) and isinstance(last_plan.get("stages"), list) else 0,
            )

        attempt_type = "INITIAL" if attempt == 0 else "REPAIR"
        timeout_sec = min(settings.mesh_request_timeout_seconds, remaining)
        llm_attempted = True

        log_learning_path_step(
            logger,
            "learning_path.step.start",
            trace_id,
            step="planner.mesh",
            attempt_number=attempt,
            attempt_type=attempt_type,
            effective_target_count=coverage.effective_target_count,
            prompt_candidate_count=prompt_candidate_count,
            timeout_seconds=round(timeout_sec, 2),
            model=model,
        )

        t_m = time.perf_counter()
        try:
            raw = await asyncio.wait_for(
                generate_learning_path_json(intent=prompt_intent, candidates=prompt_candidates, repair=repair),
                timeout=timeout_sec,
            )
            m_dur = (time.perf_counter() - t_m) * 1000
            if trace_context:
                trace_context.mesh_attempt_count += 1
                trace_context.mesh_attempt_durations_ms.append(int(m_dur))

            last_plan = raw
            stage_cnt = len(raw.get("stages", [])) if isinstance(raw, dict) and isinstance(raw.get("stages"), list) else 0

            log_learning_path_step(
                logger,
                "learning_path.step.success",
                trace_id,
                step="planner.mesh",
                duration_ms=m_dur,
                response_received=True,
                stage_count=stage_cnt,
            )

            if isinstance(raw, dict):
                log_learning_path_step(
                    logger,
                    "learning_path.step.debug",
                    trace_id,
                    step="planner.mesh_response",
                    top_level_keys=list(raw.keys()),
                    stage_count=stage_cnt,
                    stage_keys=list(raw.get("stages", [{}])[0].keys()) if stage_cnt > 0 and isinstance(raw.get("stages")[0], dict) else [],
                    response_character_count=len(json.dumps(raw)),
                )

            t_v = time.perf_counter()
            try:
                plan = LearningPathPlan.model_validate(raw)
                val_dur = (time.perf_counter() - t_v) * 1000
                log_learning_path_step(
                    logger,
                    "learning_path.step.success",
                    trace_id,
                    step="planner.schema_validation",
                    duration_ms=val_dur,
                    stage_count=len(plan.stages),
                )
            except ValidationError as val_exc:
                val_dur = (time.perf_counter() - t_v) * 1000
                last_plan = raw
                schema_errs = [
                    {
                        "location": [str(x) for x in err.get("loc", ())],
                        "type": str(err.get("type", "")),
                    }
                    for err in val_exc.errors()
                ]
                schema_validation_errors.extend(schema_errs)
                last_violations = [
                    {
                        "code": "SCHEMA_VALIDATION_ERROR",
                        "message": _sanitize_log_message(err.get("msg", "")),
                        "details": {
                            "location": [str(x) for x in err.get("loc", ())],
                            "type": str(err.get("type", "")),
                        },
                    }
                    for err in val_exc.errors()
                ]
                llm_failure_reason = "MESH_SCHEMA_VALIDATION_ERROR"
                locations = [":".join(str(x) for x in err.get("loc", ())) for err in val_exc.errors()]
                types = [str(err.get("type", "")) for err in val_exc.errors()]

                log_learning_path_step(
                    logger,
                    "learning_path.step.warning",
                    trace_id,
                    step="planner.schema_validation",
                    duration_ms=val_dur,
                    error_count=len(val_exc.errors()),
                    locations=locations,
                    types=types,
                )
                if trace_context:
                    trace_context.record_failure("planner.schema_validation", "MESH_SCHEMA_VALIDATION_ERROR")

                if attempt < settings.learning_path_max_repairs:
                    repair_count += 1
                continue

            validation = validate_learning_path_plan(
                plan.model_dump(),
                intent,
                ranked,
                exact_count=True,
                effective_target_count=coverage.effective_target_count,
            )
            if validation.valid:
                if coverage.coverage_limited:
                    status = "VALID_COVERAGE_LIMITED" if attempt == 0 else "REPAIRED_COVERAGE_LIMITED"
                else:
                    status = "VALID" if attempt == 0 else "REPAIRED_VALID"

                p_roles = {ROLE_PRIMARY: 0, ROLE_SECONDARY: 0, ROLE_CROSS_DOMAIN: 0, ROLE_SUPPORTING: 0}
                candidate_by_id = {c.course.id: c for c in ranked}
                for st in plan.stages:
                    cand = candidate_by_id.get(st.course_id)
                    if cand and cand.path_role in p_roles:
                        p_roles[cand.path_role] += 1

                log_learning_path_step(
                    logger,
                    "learning_path.step.success",
                    trace_id,
                    step="planner.validation",
                    stage_count=len(plan.stages),
                    primary=p_roles[ROLE_PRIMARY],
                    secondary=p_roles[ROLE_SECONDARY],
                    cross_domain=p_roles[ROLE_CROSS_DOMAIN],
                    supporting=p_roles[ROLE_SUPPORTING],
                    goal_coverage_status="COMPLETE",
                )

                if attempt > 0:
                    log_learning_path_step(
                        logger,
                        "learning_path.step.success",
                        trace_id,
                        step="planner.repair",
                        repair_number=attempt,
                        status="repaired_successfully",
                    )

                return PlanGenerationResult(
                    plan=plan,
                    llm_generation_used=True,
                    repair_count=repair_count,
                    deterministic_fallback_used=False,
                    validation_status=status,
                    violations=(),
                    coverage=coverage,
                    llm_attempted=True,
                    llm_failure_reason=None,
                    prompt_candidate_count=prompt_candidate_count,
                    schema_validation_errors=tuple(schema_validation_errors),
                )

            last_violations = [item.to_dict() for item in validation.violations]
            llm_failure_reason = "MESH_VALIDATION_VIOLATION"
            v_codes = [v.code for v in validation.violations]
            v_details = [v.to_dict() for v in validation.violations]

            log_learning_path_step(
                logger,
                "learning_path.step.warning",
                trace_id,
                step="planner.validation",
                violation_count=len(validation.violations),
                violation_codes=v_codes,
                violation_details=v_details,
            )
            if trace_context:
                trace_context.record_failure("planner.validation", f"VALIDATION_VIOLATION:{','.join(v_codes)}")

            if attempt < settings.learning_path_max_repairs:
                repair_count += 1
        except Exception as exc:
            m_dur = (time.perf_counter() - t_m) * 1000
            if trace_context:
                trace_context.mesh_attempt_count += 1
                trace_context.mesh_attempt_durations_ms.append(int(m_dur))
            llm_failure_reason = _classify_exception(exc)

            log_learning_path_step(
                logger,
                "learning_path.step.error",
                trace_id,
                step="planner.mesh",
                duration_ms=m_dur,
                exception_class=exc.__class__.__name__,
                classified_error=llm_failure_reason,
            )
            if trace_context:
                trace_context.record_failure("planner.mesh", llm_failure_reason)

            if attempt < settings.learning_path_max_repairs:
                repair_count += 1

    log_learning_path_step(
        logger,
        "learning_path.step.start",
        trace_id,
        step="fallback.select",
        target_count=coverage.effective_target_count,
        safe_candidate_count=len([c for c in ranked if c.path_role != ROLE_OUT_OF_DOMAIN]),
    )
    fallback_courses = select_fallback_courses(ranked, intent, profile, target_count=coverage.effective_target_count, trace_context=trace_context)
    plan = fallback_plan(fallback_courses, intent)

    validation = validate_learning_path_plan(
        plan.model_dump(),
        intent,
        ranked,
        exact_count=True,
        effective_target_count=coverage.effective_target_count,
    )
    if validation.valid:
        status = "FALLBACK_COVERAGE_LIMITED" if coverage.coverage_limited else "FALLBACK_VALID"
        log_learning_path_step(
            logger,
            "learning_path.step.success",
            trace_id,
            step="fallback.validation",
            validation_status=status,
        )
    else:
        status = "FAILED"
        v_codes = [v.code for v in validation.violations]
        v_details = [v.to_dict() for v in validation.violations]
        log_learning_path_step(
            logger,
            "learning_path.step.error",
            trace_id,
            step="fallback.validation",
            violation_codes=v_codes,
            violation_details=v_details,
        )
        if trace_context:
            trace_context.record_failure("fallback.validation", "FALLBACK_VALIDATION_FAILED")

    return PlanGenerationResult(
        plan=plan,
        llm_generation_used=False,
        repair_count=repair_count,
        deterministic_fallback_used=True,
        validation_status=status,
        violations=tuple(item.to_dict() for item in validation.violations),
        coverage=coverage,
        llm_attempted=llm_attempted,
        llm_failure_reason=llm_failure_reason,
        prompt_candidate_count=prompt_candidate_count,
        schema_validation_errors=tuple(schema_validation_errors),
    )
