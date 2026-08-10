from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.schemas.learning_path import BUDGET_TYPES
from app.services.learning_path_intent import LearningPathIntent
from app.services.learning_path_policy import (
    ROLE_CROSS_DOMAIN,
    ROLE_OUT_OF_DOMAIN,
    ROLE_PRIMARY,
    ROLE_SECONDARY,
    ROLE_SUPPORTING,
    classify_course_for_path,
    )
from app.services.recommendation_retrieval_service import RecommendationCandidate


DIFFICULTY = {"BEGINNER": 0, "INTERMEDIATE": 1, "ADVANCED": 2}


@dataclass(frozen=True)
class ValidationViolation:
    code: str
    message: str
    details: dict = None

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "details": self.details or {}}


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    violations: tuple[ValidationViolation, ...]
    classifications: tuple[dict, ...]


def _budget_limit(intent: LearningPathIntent) -> Decimal | None:
    if intent.budget_type == "CUSTOM":
        return Decimal(intent.budget_amount) if intent.budget_amount is not None else None
    return BUDGET_TYPES[intent.budget_type]


def _course_text(course) -> str:
    return " ".join((course.title, course.short_description, course.description, *(course.tags or []), *(course.what_you_will_learn or []))).casefold()


def validate_learning_path_plan(
    plan: dict,
    intent: LearningPathIntent,
    candidates: list[RecommendationCandidate],
    *,
    exact_count: bool = True,
    effective_target_count: int | None = None,
    excluded_ids: set[str] | None = None,
) -> ValidationResult:
    candidate_by_id = {candidate.course.id: candidate for candidate in candidates}
    violations: list[ValidationViolation] = []
    stages = sorted(plan.get("stages") or [], key=lambda item: item.get("position", 0))
    ids = [str(stage.get("course_id", "")) for stage in stages]
    target_count = effective_target_count if effective_target_count is not None else intent.requested_course_count
    if exact_count and len(ids) != target_count:
        violations.append(ValidationViolation("COURSE_COUNT", f"Expected exactly {target_count} stages, received {len(ids)}."))
    if len(ids) > max(intent.requested_course_count, target_count):
        violations.append(ValidationViolation("COURSE_COUNT_EXCEEDED", f"Selected count {len(ids)} exceeds target count {target_count}."))
    if len(ids) != len(set(ids)):
        violations.append(ValidationViolation("DUPLICATE_COURSE", "A course ID appears more than once."))


    classifications: list[dict] = []
    selected = []
    for position, stage in enumerate(stages, 1):
        course_id = str(stage.get("course_id", ""))
        candidate = candidate_by_id.get(course_id)
        if not candidate:
            violations.append(ValidationViolation("UNGROUNDED_COURSE", f"Stage {position} is not in the grounded candidate set.", {"course_id": course_id}))
            continue
        course = candidate.course
        if not course.is_active:
            violations.append(ValidationViolation("INACTIVE_COURSE", f"Stage {position} is inactive.", {"course_id": course.id}))
        if excluded_ids and course.id in excluded_ids:
            violations.append(ValidationViolation("EXCLUDED_COURSE", f"Stage {position} is excluded for this learner.", {"course_id": course.id}))
        role, affinities = classify_course_for_path(course, intent.primary_domain_code, intent.secondary_domain_codes)
        classifications.append({
            "position": position,
            "course_id": course.id,
            "title": course.title,
            "role": role,
            "difficulty": course.difficulty,
            "primary_affinity": affinities[intent.primary_domain_code].score,
            "secondary_affinity": max((item.score for item in affinities.values() if item.domain_code != intent.primary_domain_code), default=0.0),
        })
        selected.append((course, role, stage))
        if role == ROLE_OUT_OF_DOMAIN:
            violations.append(ValidationViolation("OUT_OF_DOMAIN", f"{course.title} does not align with the requested domains.", {"course_id": course.id}))
    if not selected:
        violations.append(ValidationViolation("EMPTY_PLAN", "The roadmap contains no grounded courses."))
    selected_goals = set()
    for _, _, stage in selected:
        stage_goals = set(stage.get("goal_codes") or [])
        unknown = stage_goals - set(intent.goal_codes)
        if unknown:
            violations.append(ValidationViolation("UNKNOWN_GOAL", "A stage references a goal not selected by the learner.", {"goal_codes": sorted(unknown)}))
        selected_goals.update(stage_goals & set(intent.goal_codes))
    missing_goals = set(intent.goal_codes) - selected_goals
    if missing_goals:
        violations.append(ValidationViolation("GOAL_COVERAGE", "The roadmap does not cover every selected learner goal.", {"missing": sorted(missing_goals)}))

    total_price = sum((Decimal(str(course.price)) for course, _, _ in selected), Decimal("0"))
    limit = _budget_limit(intent)
    if intent.budget_type == "FREE" and total_price:
        violations.append(ValidationViolation("BUDGET", "A free path contains paid courses.", {"total": str(total_price)}))
    elif intent.budget_scope == "PATH" and limit is not None and total_price > limit:
        violations.append(ValidationViolation("BUDGET", "The roadmap exceeds the requested path budget.", {"total": str(total_price), "limit": str(limit)}))
    elif intent.budget_scope == "COURSE" and limit is not None and any(course.price > limit for course, _, _ in selected):
        violations.append(ValidationViolation("COURSE_BUDGET", "A course exceeds the requested per-course budget.", {"limit": str(limit)}))

    for index, (course, _, _) in enumerate(selected):
        difficulty = DIFFICULTY.get(course.difficulty, 1)
        if index == 0 and intent.level_code in {"BEGINNER", "FAMILIAR"} and difficulty == 2:
            violations.append(ValidationViolation("DIFFICULTY_PROGRESSION", "An advanced course appears before a foundation stage."))
        if index:
            previous = selected[index - 1][0]
            previous_difficulty = DIFFICULTY.get(previous.difficulty, 1)
            if previous_difficulty - difficulty >= 2:
                violations.append(ValidationViolation("DIFFICULTY_REGRESSION", f"Stage {index + 1} regresses sharply from {previous.title}.", {"from": previous.difficulty, "to": course.difficulty}))
            if previous_difficulty == 2 and difficulty == 0 and selected[index][1] not in {ROLE_SECONDARY, ROLE_SUPPORTING, ROLE_CROSS_DOMAIN}:
                violations.append(ValidationViolation("DIFFICULTY_REGRESSION", f"Stage {index + 1} returns to beginner material without a new-domain justification."))
            prior_text = _course_text(previous)
            current_text = _course_text(course)
            same_category = previous.category.casefold() == course.category.casefold()
            shared_terms = len(set(prior_text.split()) & set(current_text.split())) >= 2
            if not same_category and not shared_terms and selected[index][1] == ROLE_OUT_OF_DOMAIN:
                violations.append(ValidationViolation("SEMANTIC_CONTINUITY", f"The transition from {previous.title} to {course.title} is not grounded."))

    return ValidationResult(not violations, tuple(violations), tuple(classifications))
