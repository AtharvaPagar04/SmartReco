import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import async_session_maker
from app.config import settings
from app.services.recommendation_ranking_service import rank_candidates
from app.services.recommendation_retrieval_service import retrieve_candidates
from app.services.recommendation_explanation_service import build_explanation

PERSONAS = {
    "cold_start": {"confidence": 0, "top_categories": [], "top_tags": [], "top_search_terms": [], "recent_course_ids": [], "excluded_course_ids": [], "signal_summary": {}},
    "python_focused": {"confidence": 0.8, "top_categories": [{"name": "Python", "score": 1}], "top_tags": [{"name": "python", "score": 1}], "top_search_terms": [{"term": "python", "score": 1}], "recent_course_ids": [], "excluded_course_ids": [], "signal_summary": {"dwell_seconds": 120}},
    "agentic_ai_focused": {"confidence": 0.8, "top_categories": [{"name": "Agentic AI", "score": 1}], "top_tags": [{"name": "agents", "score": 1}], "top_search_terms": [{"term": "agentic ai", "score": 1}], "recent_course_ids": [], "excluded_course_ids": [], "signal_summary": {"dwell_seconds": 120}},
    "cybersecurity_focused": {"confidence": 0.8, "top_categories": [{"name": "Cybersecurity", "score": 1}], "top_tags": [{"name": "security", "score": 1}], "top_search_terms": [{"term": "security", "score": 1}], "recent_course_ids": [], "excluded_course_ids": [], "signal_summary": {"dwell_seconds": 120}},
    "devops_focused": {"confidence": 0.8, "top_categories": [{"name": "DevOps", "score": 1}], "top_tags": [{"name": "devops", "score": 1}], "top_search_terms": [{"term": "devops", "score": 1}], "recent_course_ids": [], "excluded_course_ids": [], "signal_summary": {"dwell_seconds": 120}},
    "impression_only": {"confidence": 0.1, "top_categories": [], "top_tags": [], "top_search_terms": [], "recent_course_ids": [], "excluded_course_ids": [], "signal_summary": {"qualified_impressions": 20}},
    "mixed_interest": {"confidence": 0.7, "top_categories": [{"name": "Python", "score": 0.8}, {"name": "DevOps", "score": 0.7}], "top_tags": [{"name": "python", "score": 0.8}, {"name": "observability", "score": 0.6}], "top_search_terms": [{"term": "python api", "score": 1}], "recent_course_ids": [], "excluded_course_ids": [], "signal_summary": {"dwell_seconds": 180}},
    "search_heavy": {"confidence": 0.6, "top_categories": [{"name": "Data Science", "score": 1}], "top_tags": [], "top_search_terms": [{"term": "forecasting", "score": 1}, {"term": "analytics", "score": 0.8}], "recent_course_ids": [], "excluded_course_ids": [], "signal_summary": {"searches": 8}},
    "dwell_heavy": {"confidence": 0.8, "top_categories": [{"name": "Web Development", "score": 1}], "top_tags": [{"name": "fastapi", "score": 1}], "top_search_terms": [], "recent_course_ids": [], "excluded_course_ids": [], "signal_summary": {"dwell_seconds": 900}},
    "dismissed_recommendation": {"confidence": 0.8, "top_categories": [{"name": "Cybersecurity", "score": 1}], "top_tags": [{"name": "security", "score": 1}], "top_search_terms": [], "recent_course_ids": [], "excluded_course_ids": ["dismissed-course-id"], "signal_summary": {"dwell_seconds": 90}},
    "python_learning_path": {"confidence": 0.8, "top_categories": [{"name": "Python", "score": 1}], "top_tags": [{"name": "python", "score": 1}], "top_search_terms": [{"term": "agentic ai", "score": 1}], "recent_course_ids": [], "excluded_course_ids": ["python-completed"], "completed_course_ids": ["python-completed"], "completed_courses": [{"course_id": "python-completed", "title": "Python Fundamentals", "category": "Python", "difficulty": "beginner", "tags": ["python"]}], "enrolled_courses": [], "recently_viewed_courses": [], "signal_summary": {"dwell_seconds": 120}},
    "machine_learning_learning_path": {"confidence": 0.8, "top_categories": [{"name": "Machine Learning", "score": 1}], "top_tags": [{"name": "evaluation", "score": 1}], "top_search_terms": [], "recent_course_ids": [], "excluded_course_ids": ["ml-enrolled"], "enrolled_course_ids": ["ml-enrolled"], "completed_course_ids": [], "completed_courses": [], "enrolled_courses": [{"course_id": "ml-enrolled", "title": "Machine Learning Foundations", "category": "Machine Learning", "difficulty": "intermediate", "tags": ["models"]}], "recently_viewed_courses": [], "signal_summary": {"dwell_seconds": 120}},
    "cybersecurity_learning_path": {"confidence": 0.8, "top_categories": [{"name": "Cybersecurity", "score": 1}], "top_tags": [{"name": "security", "score": 1}], "top_search_terms": [{"term": "secure ai", "score": 1}], "recent_course_ids": [], "excluded_course_ids": ["security-completed"], "completed_course_ids": ["security-completed"], "completed_courses": [{"course_id": "security-completed", "title": "Cybersecurity Foundations", "category": "Cybersecurity", "difficulty": "beginner", "tags": ["security"]}], "enrolled_courses": [], "recently_viewed_courses": [], "signal_summary": {"dwell_seconds": 120}},
}


async def main(args) -> None:
    # ponytail: evaluation is offline by contract; keep it deterministic and never spend a Mesh call.
    original_key = settings.mesh_api_key
    settings.mesh_api_key = ""
    personas = PERSONAS
    if args.fixture:
        personas = json.loads(Path(args.fixture).read_text())
    results = {}
    async with async_session_maker() as db:
        for name, profile in personas.items():
            candidates, semantic, fallback = await retrieve_candidates(db, profile)
            ranked = rank_candidates(candidates, profile, limit=3)
            ids = [item.course.id for item in ranked]
            excluded = set(profile.get("excluded_course_ids", [])) | set(profile.get("completed_course_ids", [])) | set(profile.get("enrolled_course_ids", []))
            results[name] = {"valid_course_rate": 1.0 if all(item.course.is_active for item in ranked) else 0.0, "inactive_leakage": sum(not item.course.is_active for item in ranked), "duplicate_rate": 0.0 if len(ids) == len(set(ids)) else 1.0, "excluded_state_leakage": sum(item.course.id in excluded for item in ranked), "category_relevance": sum(1 for item in ranked if not profile.get("top_categories") or item.course.category.casefold() == profile["top_categories"][0]["name"].casefold()) / max(1, len(ranked)), "diversity": len({item.course.category for item in ranked}) / max(1, len(ranked)), "grounding": sum(bool(item.evidence) for item in ranked) / max(1, len(ranked)), "explanation_rate": sum(bool(build_explanation(item, profile).reason and build_explanation(item, profile).how_it_helps) for item in ranked) / max(1, len(ranked)), "fallback_success": bool(ranked) or name in {"cold_start", "impression_only"}, "mesh_calls": 0, "semantic": semantic, "sql_fallback": fallback}
    print(json.dumps(results, indent=2))
    if args.output:
        Path(args.output).write_text(json.dumps(results, indent=2) + "\n")
    settings.mesh_api_key = original_key


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fixture")
    parser.add_argument("--user-id")
    parser.add_argument("--output")
    asyncio.run(main(parser.parse_args()))
