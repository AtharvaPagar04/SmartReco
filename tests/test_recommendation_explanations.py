from types import SimpleNamespace

from app.services.recommendation_copy_service import RecommendationOutput, RecommendationOutputItem, validate_recommendation
from app.services.recommendation_explanation_service import build_explanation
from app.services.recommendation_retrieval_service import RecommendationCandidate


def test_viewed_evidence_is_not_described_as_completed():
    course = SimpleNamespace(id="next", title="Prompt Engineering", category="AI", difficulty="intermediate", tags=["prompts"], tools_used=["Python"], what_you_will_learn=["Design structured prompts"])
    candidate = RecommendationCandidate(course=course, evidence={"evidence": [{"evidence_id": "viewed:source", "type": "VIEWED_COURSE", "label": "Explored Agentic AI"}]})
    explanation = build_explanation(candidate, {})
    assert "recently explored" in explanation.reason
    assert "completed" not in explanation.reason.lower()
    assert explanation.evidence_ids == ("viewed:source",)


def test_unknown_evidence_is_rejected():
    course = SimpleNamespace(id="next", title="Prompt Engineering", category="AI", difficulty="intermediate", tags=["prompts"], is_featured=False)
    candidate = RecommendationCandidate(course=course, evidence={"evidence": [{"evidence_id": "category:ai", "type": "ENGAGED_CATEGORY", "label": "Interest in AI"}]})
    output = RecommendationOutput(headline="A useful next step", narrative="This grounded learning path connects your recent activity to a practical next skill.", recommendations=[RecommendationOutputItem(course_id="next", reason="This course adds a practical next skill to your learning path.", evidence=["invented:evidence"])])
    try:
        validate_recommendation(output, [candidate])
    except ValueError as exc:
        assert "evidence" in str(exc)
    else:
        raise AssertionError("invented evidence should be rejected")
