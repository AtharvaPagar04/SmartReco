MAX_SELECTED_DOMAINS = 3
MAX_SECONDARY_DOMAINS = 2
MAX_LEARNING_GOALS = 2

MIN_PATH_COURSES = 3
MAX_PATH_COURSES = 8

DOMAIN_SCORE_WEIGHTS = {
    "semantic": 0.35,
    "domain": 0.35,
    "goals": 0.15,
    "level": 0.10,
    "behavior": 0.05,
}

ROLE_PRIMARY = "PRIMARY"
ROLE_SECONDARY = "SECONDARY"
ROLE_CROSS_DOMAIN = "CROSS_DOMAIN"
ROLE_SUPPORTING = "SUPPORTING"
ROLE_OUT_OF_DOMAIN = "OUT_OF_DOMAIN"


from dataclasses import dataclass
import re

from app.models import Course


@dataclass(frozen=True)
class LearningPathCoverage:
    requested_count: int
    available_safe_count: int
    effective_target_count: int
    coverage_limited: bool
    coverage_reason: str | None
    primary_available: int
    secondary_available: int
    cross_domain_available: int
    supporting_available: int
    covered_domains: tuple[str, ...] = ()
    uncovered_domains: tuple[str, ...] = ()
    domain_coverage_limited: bool = False

    def to_dict(self) -> dict:
        return {
            "requested_count": self.requested_count,
            "available_safe_count": self.available_safe_count,
            "effective_target_count": self.effective_target_count,
            "coverage_limited": self.coverage_limited,
            "coverage_reason": self.coverage_reason,
            "primary_available": self.primary_available,
            "secondary_available": self.secondary_available,
            "cross_domain_available": self.cross_domain_available,
            "supporting_available": self.supporting_available,
            "eligible_course_count": self.available_safe_count,
            "covered_domains": list(self.covered_domains),
            "uncovered_domains": list(self.uncovered_domains),
            "domain_coverage_limited": self.domain_coverage_limited,
        }


@dataclass(frozen=True)
class DomainAffinity:
    domain_code: str
    score: float
    evidence: tuple[str, ...] = ()

    @property
    def tier(self) -> str:
        if self.score >= 0.72:
            return "EXACT"
        if self.score >= 0.50:
            return "STRONG"
        if self.score >= 0.25:
            return "WEAK"
        return "NONE"


def resolve_learning_path_coverage(
    candidates: list,
    intent,
) -> LearningPathCoverage:
    primary_count = 0
    secondary_count = 0
    cross_count = 0
    supporting_count = 0
    safe_course_ids = set()
    domain_affinities: dict[str, list[float]] = {}
    selected_domains = (intent.primary_domain_code, *intent.secondary_domain_codes)

    for candidate in candidates:
        role, affinities = classify_course_for_path(candidate.course, intent.primary_domain_code, intent.secondary_domain_codes)
        candidate.path_role = role
        for domain_code, affinity in affinities.items():
            domain_affinities.setdefault(domain_code, []).append(affinity.score)
        if role == ROLE_OUT_OF_DOMAIN:
            continue
        safe_course_ids.add(candidate.course.id)
        if role == ROLE_PRIMARY:
            primary_count += 1
        elif role == ROLE_SECONDARY:
            secondary_count += 1
        elif role == ROLE_CROSS_DOMAIN:
            cross_count += 1
        elif role == ROLE_SUPPORTING:
            supporting_count += 1

    available_safe_count = len(safe_course_ids)
    requested = MAX_PATH_COURSES if intent.path_length == "AUTO" else intent.requested_course_count
    chosen_target = min(requested, available_safe_count)
    is_limited = available_safe_count < requested
    reason = "CATALOG_DOMAIN_COVERAGE" if is_limited else None
    covered_domains = tuple(
        domain for domain in selected_domains
        if max(domain_affinities.get(domain, ()), default=0.0) >= 0.50
    )
    uncovered_domains = tuple(domain for domain in selected_domains if domain not in covered_domains)

    return LearningPathCoverage(
        requested_count=requested,
        available_safe_count=available_safe_count,
        effective_target_count=chosen_target,
        coverage_limited=is_limited,
        coverage_reason=reason,
        primary_available=primary_count,
        secondary_available=secondary_count,
        cross_domain_available=cross_count,
        supporting_available=supporting_count,
        covered_domains=covered_domains,
        uncovered_domains=uncovered_domains,
        domain_coverage_limited=bool(uncovered_domains),
    )


_FRONTEND_POSITIVE = (
    "frontend", "react", "next.js", "nextjs", "typescript", "javascript", "html", "css",
    "browser", "responsive", "core web vitals", "web performance", "rendering", "client-side",
    "client side", "web interface", "interface components", "ui components",
)
_FRONTEND_NEGATIVE = (
    "fastapi", "django", "flask", "backend", "server-side", "server side", "sqlalchemy",
    "microservice", "rest api", "apis", "python", "async", "database session",
)
_BACKEND_POSITIVE = (
    "backend", "fastapi", "django", "flask", "sqlalchemy", "server-side", "server side",
    "microservice", "rest api", "apis", "async", "database", "authentication",
)
_UX_POSITIVE = (
    "ui/ux", "design", "user experience", "interaction", "accessibility", "semantic html",
    "keyboard", "inclusive design", "design systems", "components", "figma", "usability",
)
_FULLSTACK_POSITIVE = ("fullstack", "full-stack", "server components", "server actions", "next.js", "nextjs")
_API_POSITIVE = ("api", "apis", "fastapi", "rest", "graphql", "async", "websocket", "sse")
_MOBILE_POSITIVE = ("mobile", "android", "ios", "react native", "flutter", "swift", "kotlin")


def _course_text(course: Course) -> str:
    values = [course.title, course.category, *(course.tags or []), *(course.what_you_will_learn or []), course.short_description, course.description, *(course.prerequisites or []), *(course.target_audience or []), *(course.tools_used or [])]
    if isinstance(course.final_project, dict):
        values.extend(str(value) for value in course.final_project.values())
    return " ".join(str(value) for value in values if value).casefold()


def _matches(text: str, phrases: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(phrase for phrase in phrases if phrase in text)


def classify_course_domain_affinity(course: Course, requested_domain: str) -> DomainAffinity:
    text = _course_text(course)
    domain = requested_domain.casefold()
    if domain == "frontend":
        positive = _matches(text, _FRONTEND_POSITIVE)
        negative = _matches(text, _FRONTEND_NEGATIVE)
        score = 0.12 + min(0.82, 0.20 * len(positive)) - min(0.72, 0.18 * len(negative))
        if not positive and negative:
            score = 0.04
        evidence = (*positive, *[f"not-{item}" for item in negative])
    elif domain == "backend":
        matches = _matches(text, _BACKEND_POSITIVE)
        score = 0.12 + min(0.88, 0.18 * len(matches))
        evidence = matches
    elif domain == "ux":
        matches = _matches(text, _UX_POSITIVE)
        score = (0.50 if course.category == "UI/UX Design" else 0.0) + min(0.50, 0.12 * len(matches))
        evidence = matches
    elif domain == "fullstack":
        matches = _matches(text, _FULLSTACK_POSITIVE)
        score = (0.20 if course.category == "Web Development" else 0.0) + min(0.80, 0.18 * len(matches))
        evidence = matches
    elif domain == "api":
        matches = _matches(text, _API_POSITIVE)
        score = min(1.0, 0.12 + 0.18 * len(matches))
        evidence = matches
    elif domain == "mobile":
        matches = _matches(text, _MOBILE_POSITIVE)
        score = min(1.0, 0.12 + 0.20 * len(matches))
        evidence = matches
    else:
        normalized = re.sub(r"[^a-z0-9]+", " ", domain).strip()
        matches = _matches(text, tuple(part for part in normalized.split() if len(part) > 2))
        category = re.sub(r"[^a-z0-9]+", " ", course.category.casefold()).strip()
        score = min(1.0, (0.50 if category == normalized else 0.0) + 0.20 * len(matches))
        evidence = matches
    return DomainAffinity(requested_domain, round(max(0.0, min(1.0, score)), 4), evidence)


def classify_course_for_path(course: Course, primary_domain: str, secondary_domains: tuple[str, ...] = ()) -> tuple[str, dict[str, DomainAffinity]]:
    primary = classify_course_domain_affinity(course, primary_domain)
    secondary = {code: classify_course_domain_affinity(course, code) for code in secondary_domains}
    best_secondary = max(secondary.values(), key=lambda value: value.score, default=None)
    if primary.score >= 0.72 and best_secondary and best_secondary.score >= 0.72:
        role = ROLE_CROSS_DOMAIN
    elif primary.score >= 0.50:
        role = ROLE_PRIMARY
    elif best_secondary and best_secondary.score >= 0.50:
        role = ROLE_SECONDARY
    elif primary.score >= 0.25 or (best_secondary and best_secondary.score >= 0.25):
        role = ROLE_SUPPORTING
    else:
        role = ROLE_OUT_OF_DOMAIN
    return role, {primary_domain: primary, **secondary}
