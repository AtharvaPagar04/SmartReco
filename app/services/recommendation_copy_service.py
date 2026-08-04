import re

from pydantic import BaseModel, Field, field_validator

from app.services.recommendation_retrieval_service import RecommendationCandidate
from app.services.recommendation_explanation_service import build_explanation


class RecommendationOutputItem(BaseModel):
    course_id: str
    reason: str = Field(min_length=15, max_length=300)
    how_it_helps: str = Field(default="", max_length=500)
    skill_connection: str = Field(default="", max_length=120)
    evidence: list[str] = Field(default_factory=list, max_length=3)
    cta_label: str = Field(default="Explore the course", min_length=2, max_length=80)

    @field_validator("reason", "how_it_helps", "skill_connection")
    @classmethod
    def no_unsupported_claims(cls, value: str) -> str:
        if re.search(r"guarantee|everyone|before it is too late|destined", value, re.I):
            raise ValueError("unsupported persuasive claim")
        return value.strip()


class RecommendationOutput(BaseModel):
    headline: str = Field(min_length=4, max_length=120)
    narrative: str = Field(min_length=40, max_length=600)
    learning_direction: str = Field(default="", max_length=120)
    recommendations: list[RecommendationOutputItem] = Field(default_factory=list, max_length=3)

    @field_validator("headline", "narrative")
    @classmethod
    def no_guarantees(cls, value: str) -> str:
        if re.search(r"guarantee|everyone|before it is too late|destined", value, re.I):
            raise ValueError("unsupported persuasive claim")
        return value.strip()


def validate_recommendation(output: RecommendationOutput, candidates: list[RecommendationCandidate], max_items: int = 3) -> RecommendationOutput:
    if not output.recommendations and candidates:
        raise ValueError("Recommendation output selected no candidates")
    allowed = {candidate.course.id for candidate in candidates}
    candidate_by_id = {candidate.course.id: candidate for candidate in candidates}
    selected = []
    seen = set()
    for item in output.recommendations:
        if item.course_id not in allowed or item.course_id in seen:
            raise ValueError("Recommendation course is not in the validated candidate set")
        candidate = candidate_by_id[item.course_id]
        if not candidate.evidence:
            raise ValueError("Recommendation has no evidence")
        allowed_evidence = {evidence.get("evidence_id") for evidence in candidate.evidence.get("evidence", []) if isinstance(evidence, dict)}
        if item.evidence and not set(item.evidence).issubset(allowed_evidence):
            raise ValueError("Recommendation evidence is not in the validated evidence set")
        explanation = build_explanation(candidate, {})
        seen.add(item.course_id)
        selected.append(item.model_copy(update={
            "how_it_helps": item.how_it_helps or explanation.how_it_helps,
            "skill_connection": item.skill_connection or explanation.skill_connection,
            "evidence": item.evidence or list(explanation.evidence_ids),
        }))
        if len(selected) == max_items:
            break

    if len(selected) < max_items and candidates:
        for candidate in candidates:
            if candidate.course.id in seen:
                continue
            explanation = build_explanation(candidate, {})
            seen.add(candidate.course.id)
            selected.append(RecommendationOutputItem(
                course_id=candidate.course.id,
                reason=explanation.reason,
                how_it_helps=explanation.how_it_helps,
                skill_connection=explanation.skill_connection,
                evidence=list(explanation.evidence_ids),
                cta_label="Explore the course",
            ))
            if len(selected) == max_items:
                break

    if not selected and candidates:
        raise ValueError("Recommendation output selected no valid candidates")
    return RecommendationOutput(headline=output.headline, narrative=output.narrative, learning_direction=output.learning_direction, recommendations=selected)


def deterministic_fallback(profile: dict, candidates: list[RecommendationCandidate], max_items: int = 3) -> RecommendationOutput:
    category = (profile.get("top_categories") or [{"name": "practical learning"}])[0]["name"]
    tags = [item["name"] for item in profile.get("top_tags", [])[:2]]
    detail = f" and {', '.join(tags)}" if tags else ""
    items = []
    for candidate in candidates[:max_items]:
        explanation = build_explanation(candidate, profile)
        items.append(RecommendationOutputItem(course_id=candidate.course.id, reason=explanation.reason, how_it_helps=explanation.how_it_helps, skill_connection=explanation.skill_connection, evidence=list(explanation.evidence_ids), cta_label="Explore the course"))
    narrative = f"Your recent course activity shows growing interest in {category}{detail}. These learning paths build on those signals with practical next steps while keeping the choice yours." if items else "Explore a few courses or try a search, and SmartReco will use those signals to tailor this section."
    return RecommendationOutput(headline=f"Continue exploring {category}", narrative=narrative, learning_direction=category, recommendations=items)
