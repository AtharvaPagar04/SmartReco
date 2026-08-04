from __future__ import annotations

from decimal import Decimal

from app.services.recommendation_retrieval_service import RecommendationCandidate


def _affinity(course, values: list[dict], field: str) -> float:
    names = {item["name"].casefold() for item in values}
    if field == "category":
        return 1.0 if course.category.casefold() in names else 0.0
    return min(1.0, sum(1 for tag in course.tags if str(tag).casefold() in names) / max(1, len(names)))


def _feedback_adjustment(course, feedback: dict) -> float:
    category = course.category.casefold()
    tags = {str(tag).casefold() for tag in (course.tags or [])}
    penalty = feedback.get("disliked_categories", {}).get(category, 0.0) * 0.18
    penalty += sum(float(feedback.get("disliked_tags", {}).get(tag, 0.0)) for tag in tags) * 0.04
    penalty = min(0.22, penalty)
    known = float(feedback.get("already_known_categories", {}).get(category, 0.0))
    practical_text = " ".join(str(value) for value in (
        getattr(course, "what_you_will_learn", None) or [],
        getattr(course, "tools_used", None) or [],
        getattr(course, "final_project", None) or {},
        getattr(course, "curriculum", None) or [],
    )).casefold()
    practical = any(word in practical_text for word in ("project", "lab", "implement", "production", "practice", "workshop", "applied"))
    adjustment = -penalty - (0.08 * known if not practical else 0.0)
    shift = int(feedback.get("preferred_difficulty_shift", 0) or 0)
    levels = {"beginner": 0, "intermediate": 1, "advanced": 2}
    level = levels.get(str(course.difficulty).casefold(), 1)
    if shift and ((shift < 0 and level <= 1) or (shift > 0 and level >= 1)):
        adjustment += 0.12
    elif shift and ((shift < 0 and level == 2) or (shift > 0 and level == 0)):
        adjustment -= 0.12
    if feedback.get("prefers_practical"):
        adjustment += 0.08 if practical else -0.04
    if feedback.get("price_sensitivity"):
        price = float(course.price or Decimal("0"))
        adjustment += 0.07 if price == 0 else max(-0.06, 0.04 - price / 1000)
    return max(-0.25, min(0.25, adjustment))


def rank_candidates(candidates: list[RecommendationCandidate], profile: dict, *, limit: int = 3) -> list[RecommendationCandidate]:
    recent = set(profile.get("recent_course_ids", []))
    completed = profile.get("completed_courses", [])
    enrolled = profile.get("enrolled_courses", [])
    viewed = profile.get("recently_viewed_courses", [])
    source_courses = [*completed, *enrolled, *viewed]
    source_categories = {str(item.get("category", "")).casefold() for item in source_courses}
    source_tags = {str(tag).casefold() for item in source_courses for tag in item.get("tags", [])}
    difficulty = {"beginner": 0, "intermediate": 1, "advanced": 2}
    for candidate in candidates:
        candidate.category_affinity = _affinity(candidate.course, profile.get("top_categories", []), "category")
        candidate.tag_affinity = _affinity(candidate.course, profile.get("top_tags", []), "tag")
        candidate.search_affinity = min(1.0, sum(1 for item in profile.get("top_search_terms", []) if item["term"].casefold() in candidate.course.title.casefold() or item["term"].casefold() in candidate.course.category.casefold()))
        candidate.dwell_affinity = min(1.0, profile.get("signal_summary", {}).get("dwell_seconds", 0) / 600)
        candidate.novelty_score = 0.0 if candidate.course.id in recent else 1.0
        candidate.recently_viewed_penalty = 0.12 if candidate.course.id in recent else 0.0
        candidate.featured_boost = 0.04 if candidate.course.is_featured else 0.0
        candidate.progression_score = min(1.0, 0.55 * (1.0 if candidate.course.category.casefold() in source_categories else 0.0) + 0.45 * (len({str(tag).casefold() for tag in candidate.course.tags} & source_tags) / max(1, len(source_tags))))
        source_levels = [difficulty.get(str(item.get("difficulty", "")).casefold(), 1) for item in source_courses]
        candidate.difficulty_fit = 1.0 if not source_levels else max(0.0, 1.0 - abs(difficulty.get(str(candidate.course.difficulty).casefold(), 1) - max(source_levels)) * 0.35)
        candidate.practical_fit = 1.0 if (getattr(candidate.course, "tools_used", None) or getattr(candidate.course, "what_you_will_learn", None)) else 0.5
        base_score = min(1.0, max(0.0, 0.30 * (candidate.semantic_score or 0) + 0.25 * candidate.progression_score + 0.15 * candidate.category_affinity + 0.10 * candidate.search_affinity + 0.05 * candidate.difficulty_fit + 0.05 * candidate.practical_fit + 0.05 * candidate.tag_affinity + 0.05 * candidate.novelty_score + candidate.featured_boost - candidate.recently_viewed_penalty))
        candidate.base_personalized_score = round(base_score, 6)
        candidate.feedback_adjustment = _feedback_adjustment(candidate.course, profile.get("recommendation_feedback", {}))
        feedback_score = min(1.0, max(0.0, base_score + candidate.feedback_adjustment))
        candidate.feedback_score = round(feedback_score, 6)
        candidate.deterministic_score = round(0.75 * base_score + 0.25 * feedback_score, 6)
        evidence = []
        for kind, items, label_prefix in (("COMPLETED_COURSE", completed, "Completed"), ("ENROLLED_COURSE", enrolled, "Currently learning"), ("VIEWED_COURSE", viewed, "Explored")):
            for item in items[:3]:
                if item.get("course_id"):
                    evidence.append({"evidence_id": f"{kind.lower()}:{item['course_id']}", "type": kind, "course_id": item["course_id"], "label": f"{label_prefix} {item['title']}"})
        for search in profile.get("top_search_terms", [])[:2]:
            term = str(search.get("term", "")).casefold()
            if term and (term in candidate.course.title.casefold() or term in candidate.course.category.casefold() or any(term in str(tag).casefold() for tag in candidate.course.tags)):
                evidence.append({"evidence_id": f"search:{term}", "type": "SEARCHED_TOPIC", "label": f"Searched for {search['term']}"})
        if not evidence and candidate.category_affinity:
            evidence.append({"evidence_id": f"category:{candidate.course.category.casefold()}", "type": "ENGAGED_CATEGORY", "label": f"Interest in {candidate.course.category}"})
        candidate.evidence.update({"evidence": evidence[:3], "matched_categories": [candidate.course.category] if candidate.category_affinity else [], "matched_tags": [str(tag) for tag in candidate.course.tags if str(tag).casefold() in {item["name"].casefold() for item in profile.get("top_tags", [])}], "dwell_seconds": profile.get("signal_summary", {}).get("dwell_seconds", 0), "retrieval_sources": candidate.retrieval_sources})
    ordered = sorted(candidates, key=lambda item: (-item.deterministic_score, item.course.category, item.course.title, item.course.id))
    result: list[RecommendationCandidate] = []
    category_counts: dict[str, int] = {}
    for candidate in ordered:
        category = candidate.course.category
        if category_counts.get(category, 0) >= 2 and (profile.get("top_categories") or [{}])[0].get("score", 0) < 0.75:
            continue
        result.append(candidate)
        category_counts[category] = category_counts.get(category, 0) + 1
        if len(result) == limit:
            break
    return result
