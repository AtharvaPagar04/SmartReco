from dataclasses import dataclass

from app.services.recommendation_retrieval_service import RecommendationCandidate


@dataclass(frozen=True)
class RetrievalQuality:
    outcome: str
    average_score: float
    matched_count: int
    candidate_count: int


def evaluate_retrieval(candidates: list[RecommendationCandidate], profile: dict) -> RetrievalQuality:
    if not candidates:
        return RetrievalQuality("FALLBACK", 0.0, 0, 0)
    scores = [candidate.deterministic_score for candidate in candidates]
    matched = sum(bool(candidate.category_affinity or candidate.tag_affinity or candidate.search_affinity) for candidate in candidates)
    average = sum(scores) / len(scores)
    if len(candidates) >= 5 and average >= 0.25 and matched >= 3:
        outcome = "GOOD"
    elif matched or average >= 0.12:
        outcome = "REFINE"
    else:
        outcome = "FALLBACK"
    return RetrievalQuality(outcome, round(average, 6), matched, len(candidates))


def refine_profile(profile: dict) -> dict:
    refined = {**profile}
    refined["top_search_terms"] = list(profile.get("top_search_terms", []))[:2]
    refined["top_categories"] = list(profile.get("top_categories", []))[:2]
    refined["top_tags"] = list(profile.get("top_tags", []))[:4]
    return refined
