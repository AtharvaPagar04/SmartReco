from types import SimpleNamespace

from app.services.recommendation_ranking_service import rank_candidates
from app.services.recommendation_retrieval_service import RecommendationCandidate


def course(course_id, title, category="AI", difficulty="intermediate", tags=None):
    return SimpleNamespace(id=course_id, title=title, category=category, difficulty=difficulty, tags=tags or ["ai"], is_featured=False, tools_used=["Python"], what_you_will_learn=["Build practical workflows"])


def test_completed_and_enrolled_ids_are_hard_exclusion_inputs():
    profile = {
        "completed_course_ids": ["completed"],
        "enrolled_course_ids": ["enrolled"],
        "excluded_course_ids": ["completed", "enrolled"],
        "completed_courses": [{"course_id": "completed", "title": "Python Fundamentals", "category": "Python", "difficulty": "beginner", "tags": ["python"]}],
        "enrolled_courses": [{"course_id": "enrolled", "title": "Agentic AI", "category": "AI", "difficulty": "intermediate", "tags": ["agents"]}],
        "recently_viewed_courses": [],
        "top_categories": [{"name": "Python", "score": 1}],
        "top_tags": [],
        "top_search_terms": [],
        "recent_course_ids": [],
        "signal_summary": {},
    }
    candidates = [RecommendationCandidate(course("next", "Applied Python", "Python"), semantic_score=.8, evidence={"fallback": True})]
    assert {"completed", "enrolled"}.issubset(profile["excluded_course_ids"])
    assert rank_candidates(candidates, profile, limit=1)[0].course.id not in profile["excluded_course_ids"]


def test_ranking_is_stable_for_same_learning_context():
    profile = {"top_categories": [{"name": "AI", "score": 1}], "top_tags": [], "top_search_terms": [], "recent_course_ids": [], "signal_summary": {}, "completed_courses": [], "enrolled_courses": [], "recently_viewed_courses": []}
    candidates = [RecommendationCandidate(course("b", "B"), semantic_score=.5, evidence={"fallback": True}), RecommendationCandidate(course("a", "A"), semantic_score=.5, evidence={"fallback": True})]
    assert [item.course.id for item in rank_candidates(candidates, profile, limit=2)] == ["a", "b"]
