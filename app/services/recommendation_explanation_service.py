from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RecommendationExplanation:
    reason: str
    how_it_helps: str
    skill_connection: str
    evidence_labels: tuple[str, ...]
    evidence_ids: tuple[str, ...]


def _evidence(candidate, profile: dict) -> list[dict]:
    value = candidate.evidence.get("evidence", []) if isinstance(candidate.evidence, dict) else []
    return [item for item in value if isinstance(item, dict) and item.get("evidence_id")][:3]


def build_explanation(candidate, profile: dict) -> RecommendationExplanation:
    course = candidate.course
    evidence = _evidence(candidate, profile)
    completed = next((item for item in evidence if item.get("type") == "COMPLETED_COURSE"), None)
    enrolled = next((item for item in evidence if item.get("type") in {"ENROLLED_COURSE", "CONTINUED_COURSE"}), None)
    viewed = next((item for item in evidence if item.get("type") == "VIEWED_COURSE"), None)
    source = completed or enrolled or viewed
    source_title = source.get("label", "your recent learning") if source else "your recent learning"
    category = course.category or "practical learning"
    tags = [str(tag) for tag in (getattr(course, "tags", None) or [])[:3]]
    tools = [str(tool) for tool in (getattr(course, "tools_used", None) or [])[:2]]
    additions = ", ".join(tags or tools or [category])
    if completed:
        reason = f"You completed {source_title.removeprefix('Completed ')}, and this course is a suitable next step in {category}."
        connection = f"{source_title.removeprefix('Completed ')} → {category}"
    elif enrolled:
        reason = f"You are currently learning {source_title.removeprefix('Currently learning ')}, so this adds a complementary {category} skill."
        connection = f"{source_title.removeprefix('Currently learning ')} → {category}"
    elif viewed:
        reason = f"You recently explored {source_title.removeprefix('Explored ')}, and this course develops a related {category} skill."
        connection = f"Explored → {category}"
    else:
        reason = f"Your recent activity shows interest in {category}, and this course offers a practical next step."
        connection = f"Interest → {category}"
    outcomes = [str(item) for item in (getattr(course, "what_you_will_learn", None) or [])[:2]]
    benefit = ", ".join(outcomes) if outcomes else f"build skills in {additions}"
    how = f"It helps you {benefit.lower()} and connect your current learning to practical {category} work."
    labels = tuple(item.get("label", "") for item in evidence if item.get("label"))
    ids = tuple(item["evidence_id"] for item in evidence)
    return RecommendationExplanation(reason[:300], how[:500], connection[:120], labels, ids)
