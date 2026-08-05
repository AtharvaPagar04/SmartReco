from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models import Course, LearningPath, LearningPathGenerationRun, LearningPathItem, User
from app.schemas.learning_path import DOMAIN_BY_CODE, FORMAT_PREFERENCES, GOALS, LEVELS, PREFERENCES, PRIOR_SKILLS, LearningPathInput
from app.services.interest_profile_service import build_or_refresh_profile
from app.services.learning_path_policy import MAX_PATH_COURSES, MIN_PATH_COURSES
from app.services.recommendation_retrieval_service import RecommendationCandidate, retrieve_candidates, retrieve_sql_fallback

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.-]*", re.I)
DIFFICULTY = {"BEGINNER": 0, "INTERMEDIATE": 1, "ADVANCED": 2}
STAGES = ("Build the foundation", "Strengthen the core skill", "Apply the skill", "Build production confidence", "Extend your capability", "Practice at depth", "Complete a capstone step", "Keep progressing")


def _tokens(value: str) -> set[str]:
    return {item.casefold() for item in TOKEN_RE.findall(value or "") if len(item) > 1}


def _hours(course: Course) -> int:
    return max(1, math.ceil(course.total_curriculum_minutes / 60))


def _budget(path_input: LearningPathInput) -> Decimal | None:
    return path_input.effective_budget()


def _profile_for_input(path_input: LearningPathInput, profile: dict) -> dict:
    domains = [DOMAIN_BY_CODE[path_input.primary_domain], *(DOMAIN_BY_CODE[code] for code in path_input.secondary_domains)]
    categories = [item for domain in domains for item in domain.categories]
    tags = [item for domain in domains for item in domain.tags]
    goal = GOALS[path_input.goal]
    terms = [goal, *(FORMAT_PREFERENCES[item] for item in path_input.format_preferences), *(PREFERENCES[item] for item in path_input.learning_preferences), *(PRIOR_SKILLS[item] for item in path_input.prior_skills)]
    if path_input.optional_instruction:
        terms.append(path_input.optional_instruction)
    merged = dict(profile)
    merged["top_categories"] = [{"name": value} for value in dict.fromkeys(categories)] + profile.get("top_categories", [])[:3]
    merged["top_tags"] = [{"name": value} for value in dict.fromkeys(tags)] + profile.get("top_tags", [])[:5]
    merged["top_search_terms"] = [{"term": value} for value in terms] + profile.get("top_search_terms", [])[:3]
    merged["confidence"] = 1.0
    return merged


def _score(course: Course, path_input: LearningPathInput, profile: dict) -> float:
    domains = [DOMAIN_BY_CODE[path_input.primary_domain], *(DOMAIN_BY_CODE[code] for code in path_input.secondary_domains)]
    explicit = _tokens(" ".join(item for domain in domains for item in (domain.label, *domain.categories, *domain.tags)))
    explicit |= _tokens(" ".join((GOALS[path_input.goal], *(PREFERENCES[item] for item in path_input.learning_preferences), *(PRIOR_SKILLS[item] for item in path_input.prior_skills), *(FORMAT_PREFERENCES[item] for item in path_input.format_preferences), path_input.optional_instruction)))
    text = _tokens(" ".join((course.title, course.category, *(course.tags or []), *(course.what_you_will_learn or []), course.short_description, course.description)))
    score = 45.0 * len(explicit & text) / max(1, len(explicit))
    for index, domain in enumerate(domains):
        weight = 25 if index == 0 else 8
        if course.category in domain.categories:
            score += weight
        score += (8 if index == 0 else 3) * len({_item.casefold() for _item in course.tags or []} & {tag.casefold() for tag in domain.tags})
    level = {"BEGINNER": 0, "FAMILIAR": 0, "FOUNDATIONS": 1, "INTERMEDIATE": 1, "ADVANCED": 2}[path_input.level]
    score += max(0, 12 - abs(DIFFICULTY.get(course.difficulty, 1) - level) * 5)
    if "PROJECTS" in path_input.learning_preferences and course.final_project:
        score += 8
    if "PRODUCTION" in path_input.learning_preferences and any(word in text for word in {"production", "reliability", "deployment", "operations"}):
        score += 7
    if profile.get("top_categories") and course.category.casefold() == str(profile["top_categories"][0].get("name", "")).casefold():
        score += 4
    return score


def _eligible(course: Course, path_input: LearningPathInput, excluded: set[str], total: Decimal) -> bool:
    if not course.is_active or course.id in excluded:
        return False
    budget = _budget(path_input)
    if path_input.budget_type == "FREE" and course.price != 0:
        return False
    if path_input.budget_scope == "COURSE" and budget is not None and course.price > budget:
        return False
    if path_input.budget_scope == "PATH" and budget is not None and total + Decimal(str(course.price)) > budget:
        return False
    return True


def _path_bounds(path_input: LearningPathInput) -> tuple[int, int]:
    if path_input.path_length == "FOCUSED":
        target_min, target_max = 3, 4
    elif path_input.path_length == "BALANCED":
        target_min, target_max = 6, 7
    elif path_input.path_length in ("EXTENDED", "DEEP"):
        target_min, target_max = 8, 8
    else:
        if path_input.requested_course_count in (3, 4):
            target_min, target_max = 3, 4
        elif path_input.requested_course_count in (6, 7):
            target_min, target_max = 6, 7
        elif path_input.requested_course_count >= 8:
            target_min, target_max = 8, 8
        elif (path_input.target_weeks and path_input.target_weeks <= 4) or path_input.weekly_hours < 5:
            target_min, target_max = 3, 4
        elif (path_input.target_weeks and path_input.target_weeks >= 12) or path_input.weekly_hours >= 15:
            target_min, target_max = 6, 8
        else:
            target_min, target_max = 3, 8
    target_max = min(target_max, settings.learning_path_max_courses, MAX_PATH_COURSES)
    target_min = min(target_min, target_max)
    return target_min, target_max


def _select_courses(candidates: list[RecommendationCandidate], path_input: LearningPathInput, profile: dict) -> list[Course]:
    excluded = set(profile.get("excluded_course_ids", []))
    minimum, maximum = _path_bounds(path_input)
    target = maximum
    ordered = sorted(candidates, key=lambda item: (-_score(item.course, path_input, profile), DIFFICULTY.get(item.course.difficulty, 1), item.course.title.casefold(), item.course.id))
    chosen: list[Course] = []
    total = Decimal("0.00")
    for candidate in ordered:
        course = candidate.course
        if chosen and _score(course, path_input, profile) < 18:
            continue
        if not _eligible(course, path_input, excluded | {item.id for item in chosen}, total):
            continue
        chosen.append(course)
        total += Decimal(str(course.price))
        if len(chosen) == target:
            break
    if len(chosen) < minimum:
        return chosen
    return chosen[:maximum]


def _reason(course: Course, previous: Course | None, domain_label: str) -> str:
    skills = ", ".join((course.what_you_will_learn or course.tags or [])[:3]) or course.category
    if previous:
        return f"{course.title} adds {skills}, building on {previous.title} for the {domain_label} goal."
    return f"{course.title} is a grounded first step because it covers {skills} for the {domain_label} goal."


def _next_text(course: Course, next_course: Course | None) -> str:
    if not next_course:
        return "This is the final planned stage; use its course outcome as the practical next step."
    return f"The skills from this course provide a base for {next_course.title}, which is the next stage in the sequence."


async def candidate_courses(db: AsyncSession, user: User, path_input: LearningPathInput) -> tuple[list[RecommendationCandidate], str | None, bool]:
    profile_row = await build_or_refresh_profile(db, user.id)
    profile = _profile_for_input(path_input, profile_row.profile_json or {})
    candidates, used_semantic, used_sql_fallback = await retrieve_candidates(db, profile, limit=settings.learning_path_max_candidates)
    by_id = {item.course.id: item for item in candidates}
    if len(by_id) < settings.learning_path_max_candidates:
        for item in await retrieve_sql_fallback(db, profile, limit=settings.learning_path_max_candidates):
            by_id.setdefault(item.course.id, item)
    return list(by_id.values()), profile_row.profile_hash, used_semantic and not used_sql_fallback


async def create_learning_path(db: AsyncSession, user: User, path_input: LearningPathInput, *, status: str = "READY") -> LearningPath:
    candidates, profile_hash, used_mesh = await candidate_courses(db, user, path_input)
    profile = _profile_for_input(path_input, {})
    # candidate_courses already applied the user-specific hard exclusions through retrieval.
    courses = _select_courses(candidates, path_input, profile)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    domain = DOMAIN_BY_CODE[path_input.primary_domain]
    total_minutes = sum(course.total_curriculum_minutes for course in courses)
    total_price = sum((Decimal(str(course.price)) for course in courses), Decimal("0.00"))
    total_hours = max(1, math.ceil(total_minutes / 60)) if courses else 0
    weeks = math.ceil(total_minutes / (path_input.weekly_hours * 60)) if courses else 0
    path = LearningPath(
        user_id=user.id,
        title=f"Your {domain.label} learning path",
        summary=f"A {GOALS[path_input.goal].lower()} route shaped around {LEVELS[path_input.level].lower()}, {path_input.weekly_hours} hours a week, and the available course catalog.",
        status=status,
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
        profile_hash=profile_hash,
        used_mesh=used_mesh,
        used_fallback=not used_mesh,
        estimated_total_hours=total_hours,
        estimated_weeks=weeks,
        total_price=total_price,
        generated_at=now,
    )
    db.add(path)
    await db.flush()
    for index, course in enumerate(courses, 1):
        previous = courses[index - 2] if index > 1 else None
        following = courses[index] if index < len(courses) else None
        db.add(LearningPathItem(
            learning_path_id=path.id,
            course_id=course.id,
            position=index,
            stage_label=STAGES[min(index - 1, len(STAGES) - 1)],
            reason=_reason(course, previous, domain.label),
            how_it_prepares_next=_next_text(course, following),
            skills_gained_json=list((course.what_you_will_learn or course.tags or [])[:5]),
            estimated_hours=_hours(course),
            price_snapshot=course.price,
            currency=course.currency,
        ))
    db.add(LearningPathGenerationRun(learning_path_id=path.id, status="SUCCEEDED", candidate_count=len(candidates), selected_count=len(courses), used_fallback=not used_mesh, started_at=now, completed_at=now))
    await db.flush()
    return path


async def get_owned_path(db: AsyncSession, user_id: str, path_id: str) -> LearningPath | None:
    return await db.scalar(select(LearningPath).options(selectinload(LearningPath.items).selectinload(LearningPathItem.course)).where(LearningPath.id == path_id, LearningPath.user_id == user_id))


async def replace_item(db: AsyncSession, path: LearningPath, item: LearningPathItem, reason: str) -> bool:
    path_input = LearningPathInput.model_validate(path.input_json)
    candidates, _, _ = await candidate_courses(db, await db.scalar(select(User).where(User.id == path.user_id)), path_input)
    excluded = {path_item.course_id for path_item in path.items}
    candidates = [candidate for candidate in candidates if candidate.course.id not in excluded]
    if reason == "TOO_ADVANCED":
        candidates.sort(key=lambda candidate: (DIFFICULTY.get(candidate.course.difficulty, 1), -_score(candidate.course, path_input, {}), candidate.course.title.casefold()))
    elif reason == "TOO_EXPENSIVE":
        candidates.sort(key=lambda candidate: (candidate.course.price, -_score(candidate.course, path_input, {}), candidate.course.title.casefold()))
    else:
        candidates.sort(key=lambda candidate: (-_score(candidate.course, path_input, {}), DIFFICULTY.get(candidate.course.difficulty, 1), candidate.course.title.casefold()))
    if not candidates:
        return False
    course = candidates[0].course
    item.course_id = course.id
    item.course = course
    item.reason = _reason(course, None, DOMAIN_BY_CODE[path_input.primary_domain].label)
    item.skills_gained_json = list((course.what_you_will_learn or course.tags or [])[:5])
    item.estimated_hours = _hours(course)
    item.price_snapshot = course.price
    item.currency = course.currency
    path.total_price = sum((Decimal(str(path_item.price_snapshot)) for path_item in path.items), Decimal("0.00"))
    path.estimated_total_hours = sum(_hours(path_item.course) for path_item in path.items if path_item.course)
    path.estimated_weeks = math.ceil(path.estimated_total_hours / path.weekly_hours)
    await db.flush()
    return True
