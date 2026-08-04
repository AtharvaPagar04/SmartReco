from __future__ import annotations

import asyncio
from typing import Any, TypedDict
from types import SimpleNamespace

import openai
from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.services.mesh_chat_service import MeshChatError, generate_json
from app.services.mesh_client import MeshConfigurationError
from app.services.recommendation_copy_service import RecommendationOutput, deterministic_fallback, validate_recommendation
from app.services.recommendation_persistence_service import fail_run, persist_run
from app.services.recommendation_quality_service import evaluate_retrieval, refine_profile
from app.services.recommendation_ranking_service import rank_candidates
from app.services.recommendation_retrieval_service import RecommendationCandidate, retrieve_candidates


class RecommendationGraphState(TypedDict, total=False):
    run_id: str
    user_id: str
    trigger_type: str
    profile: dict
    profile_hash: str
    retrieval_query: str
    candidates: list[dict]
    ranked_candidates: list[dict]
    retrieval_quality: str
    refinement_count: int
    model_output: dict | None
    validated_output: dict | None
    used_semantic_retrieval: bool
    used_sql_fallback: bool
    used_llm_fallback: bool
    repair_count: int
    errors: list[dict]
    mesh_deadline: float
    llm_called: bool


def _candidate_dict(candidate: RecommendationCandidate) -> dict:
    return {"course_id": candidate.course.id, "title": candidate.course.title, "category": candidate.course.category, "difficulty": candidate.course.difficulty, "price": float(candidate.course.price), "currency": candidate.course.currency, "tags": list(candidate.course.tags or [])[:8], "tools_used": list(getattr(candidate.course, "tools_used", None) or [])[:6], "what_you_will_learn": list(getattr(candidate.course, "what_you_will_learn", None) or [])[:4], "prerequisites": list(getattr(candidate.course, "prerequisites", None) or [])[:3], "instructor": candidate.course.instructor, "duration_minutes": candidate.course.duration_minutes, "base_personalized_score": candidate.base_personalized_score, "feedback_adjustment": candidate.feedback_adjustment, "feedback_score": candidate.feedback_score, "deterministic_score": candidate.deterministic_score, "semantic_score": candidate.semantic_score, "retrieval_sources": candidate.retrieval_sources, "evidence": candidate.evidence}


def _candidate_objects(items: list[dict]) -> list[RecommendationCandidate]:
    result = []
    for item in items:
        course = SimpleNamespace(id=item["course_id"], title=item["title"], category=item["category"], difficulty=item["difficulty"], price=item["price"], currency=item["currency"], tags=item.get("tags", []), tools_used=item.get("tools_used", []), what_you_will_learn=item.get("what_you_will_learn", []), prerequisites=item.get("prerequisites", []), instructor=item.get("instructor", ""), duration_minutes=item.get("duration_minutes", 0), is_featured=False)
        result.append(RecommendationCandidate(course=course, semantic_score=item.get("semantic_score"), deterministic_score=item.get("deterministic_score", 0), retrieval_sources=item.get("retrieval_sources", []), evidence=item.get("evidence", {})))
    return result


def build_recommendation_graph(db):
    graph = StateGraph(RecommendationGraphState)

    async def load_or_build_profile(state):
        from app.models import UserInterestProfile
        profile_row = await db.scalar(__import__("sqlalchemy", fromlist=["select"]).select(UserInterestProfile).where(UserInterestProfile.user_id == state["user_id"]))
        if not profile_row:
            from app.services.interest_profile_service import build_or_refresh_profile
            profile_row = await build_or_refresh_profile(db, state["user_id"])
        return {"profile": profile_row.profile_json, "profile_hash": profile_row.profile_hash, "refinement_count": 0, "repair_count": 0, "errors": []}

    async def build_query(state):
        from app.services.recommendation_retrieval_service import build_retrieval_query
        return {"retrieval_query": build_retrieval_query(state["profile"])}

    async def retrieve(state):
        candidates, semantic, fallback = await retrieve_candidates(db, state["profile"])
        return {"candidates": [_candidate_dict(candidate) for candidate in candidates], "used_semantic_retrieval": semantic, "used_sql_fallback": fallback}

    async def rank(state):
        ranked = rank_candidates(_candidate_objects(state.get("candidates", [])), state["profile"], limit=settings.recommendation_final_count * 4)
        return {"ranked_candidates": [_candidate_dict(candidate) for candidate in ranked]}

    async def evaluate(state):
        quality = evaluate_retrieval(_candidate_objects(state.get("ranked_candidates", [])), state["profile"])
        return {"retrieval_quality": quality.outcome}

    async def refine(state):
        profile = refine_profile(state["profile"])
        candidates, semantic, fallback = await retrieve_candidates(db, profile)
        ranked = rank_candidates(_candidate_objects([_candidate_dict(candidate) for candidate in candidates]), profile, limit=settings.recommendation_final_count * 4)
        return {"profile": profile, "candidates": [_candidate_dict(candidate) for candidate in candidates], "ranked_candidates": [_candidate_dict(candidate) for candidate in ranked], "refinement_count": state.get("refinement_count", 0) + 1, "used_semantic_retrieval": semantic, "used_sql_fallback": fallback}

    async def prepare_context(state):
        return {"mesh_deadline": asyncio.get_running_loop().time() + settings.mesh_total_budget_seconds}

    async def generate(state):
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import select
        from app.models import RecommendationItem, RecommendationRun
        from app.services.recommendation_persistence_service import cache_key

        candidate_ids = [c["course_id"] for c in state.get("ranked_candidates", [])[: settings.recommendation_max_candidates]]
        key = cache_key(
            user_id=state["user_id"],
            profile_hash=state["profile_hash"],
            candidate_ids=candidate_ids,
            model_name=settings.mesh_chat_model,
        )
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        ttl_cutoff = now - timedelta(hours=settings.recommendation_ttl_hours)
        cached_run = await db.scalar(
            select(RecommendationRun)
            .where(
                RecommendationRun.user_id == state["user_id"],
                RecommendationRun.cache_key == key,
                RecommendationRun.status.in_(("SUCCEEDED", "FALLBACK_SUCCEEDED")),
                RecommendationRun.completed_at >= ttl_cutoff,
            )
            .order_by(RecommendationRun.completed_at.desc())
            .limit(1)
        )
        if cached_run and cached_run.headline and cached_run.narrative:
            items_rows = (
                await db.scalars(
                    select(RecommendationItem)
                    .where(RecommendationItem.run_id == cached_run.id)
                    .order_by(RecommendationItem.rank)
                )
            ).all()
            if items_rows:
                output = {
                    "headline": cached_run.headline,
                    "narrative": cached_run.narrative,
                    "learning_direction": (state.get("profile", {}).get("top_categories") or [{"name": "practical learning"}])[0].get("name", "practical learning"),
                    "recommendations": [
                        {"course_id": item.course_id, "reason": item.reason, "how_it_helps": (item.evidence_json or {}).get("how_it_helps", ""), "skill_connection": (item.evidence_json or {}).get("skill_connection", ""), "evidence": [e.get("evidence_id") for e in (item.evidence_json or {}).get("evidence", []) if isinstance(e, dict)], "cta_label": item.cta_label}
                        for item in items_rows
                    ],
                }
                return {"model_output": output, "validated_output": output, "used_llm_fallback": cached_run.used_llm_fallback}

        if not settings.mesh_api_key or not settings.mesh_chat_model:
            try:
                output = await generate_json(profile=state["profile"], candidates=state.get("ranked_candidates", [])[: settings.recommendation_max_candidates], repair=state.get("repair_count", 0) > 0)
                return {"model_output": output, "llm_called": False}
            except MeshConfigurationError:
                return {"errors": [*state.get("errors", []), {"code": "mesh_not_configured", "message": "Mesh chat is not configured"}], "llm_called": False}

        deadline = state.get("mesh_deadline") or (asyncio.get_running_loop().time() + settings.mesh_total_budget_seconds)
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return {"errors": [*state.get("errors", []), {"code": "mesh_total_timeout", "message": "Mesh generation budget expired"}], "llm_called": True}
        try:
            async with asyncio.timeout(remaining):
                output = await generate_json(profile=state["profile"], candidates=state.get("ranked_candidates", [])[: settings.recommendation_max_candidates], repair=state.get("repair_count", 0) > 0)
            return {"model_output": output, "llm_called": True}
        except MeshConfigurationError:
            return {"errors": [*state.get("errors", []), {"code": "mesh_not_configured", "message": "Mesh chat is not configured"}], "llm_called": False}
        except MeshChatError as exc:
            return {"errors": [*state.get("errors", []), {"code": exc.code, "message": str(exc)}], "llm_called": True}
        except openai.APITimeoutError:
            return {"errors": [*state.get("errors", []), {"code": "mesh_provider_timeout", "message": "Mesh request timed out"}], "llm_called": True}
        except openai.APIConnectionError:
            return {"errors": [*state.get("errors", []), {"code": "mesh_connection_failed", "message": "Mesh connection failed"}], "llm_called": True}
        except openai.APIStatusError as exc:
            status_code = getattr(exc, "status_code", 0)
            code = "mesh_retryable_status" if status_code == 429 or status_code >= 500 else "mesh_status_error"
            return {"errors": [*state.get("errors", []), {"code": code, "message": "Mesh provider returned an error"}], "llm_called": True}
        except TimeoutError:
            return {"errors": [*state.get("errors", []), {"code": "mesh_total_timeout", "message": "Mesh generation budget expired"}], "llm_called": True}


    async def validate(state):
        if not state.get("model_output"):
            return {}
        try:
            parsed = RecommendationOutput.model_validate(state.get("model_output") or {})
            valid = validate_recommendation(parsed, _candidate_objects(state.get("ranked_candidates", [])), settings.recommendation_final_count)
            return {"validated_output": valid.model_dump(), "errors": []}
        except Exception as exc:
            return {"errors": [*state.get("errors", []), {"code": "invalid_model_output", "message": str(exc)}]}

    async def fallback(state):
        output = deterministic_fallback(state["profile"], _candidate_objects(state.get("ranked_candidates", [])), settings.recommendation_final_count)
        return {"validated_output": output.model_dump(), "used_llm_fallback": True}

    async def persist(state):
        try:
            output = RecommendationOutput.model_validate(state["validated_output"])
            await persist_run(db, state["run_id"], output, state.get("ranked_candidates", []), used_semantic=state.get("used_semantic_retrieval", False), used_sql_fallback=state.get("used_sql_fallback", False), used_llm_fallback=state.get("used_llm_fallback", False), refinement_count=state.get("refinement_count", 0), quality=state.get("retrieval_quality", "FALLBACK"), graph_errors=state.get("errors", []))
        except Exception as exc:
            await fail_run(db, state["run_id"], "persistence_failed", str(exc))
        return {}

    def after_quality(state):
        if state.get("retrieval_quality") == "REFINE" and state.get("refinement_count", 0) < settings.recommendation_max_refinements:
            return "refine_retrieval"
        return "prepare_model_context"

    def after_validation(state):
        if state.get("validated_output"):
            return "persist_recommendation"
        if state.get("repair_count", 0) < 1 and state.get("model_output") is not None:
            return "repair_recommendation"
        return "generate_fallback_copy"

    async def repair(state):
        result = await generate({**state, "repair_count": state.get("repair_count", 0) + 1})
        return {**result, "repair_count": state.get("repair_count", 0) + 1}

    graph.add_node("load_or_build_profile", load_or_build_profile)
    graph.add_node("build_retrieval_query", build_query)
    graph.add_node("retrieve_candidates", retrieve)
    graph.add_node("rank_candidates", rank)
    graph.add_node("evaluate_retrieval", evaluate)
    graph.add_node("refine_retrieval", refine)
    graph.add_node("prepare_model_context", prepare_context)
    graph.add_node("generate_recommendation", generate)
    graph.add_node("repair_recommendation", repair)
    graph.add_node("validate_recommendation", validate)
    graph.add_node("generate_fallback_copy", fallback)
    graph.add_node("persist_recommendation", persist)
    graph.add_edge(START, "load_or_build_profile")
    graph.add_edge("load_or_build_profile", "build_retrieval_query")
    graph.add_edge("build_retrieval_query", "retrieve_candidates")
    graph.add_edge("retrieve_candidates", "rank_candidates")
    graph.add_edge("rank_candidates", "evaluate_retrieval")
    graph.add_conditional_edges("evaluate_retrieval", after_quality)
    graph.add_edge("refine_retrieval", "evaluate_retrieval")
    graph.add_edge("prepare_model_context", "generate_recommendation")
    graph.add_edge("generate_recommendation", "validate_recommendation")
    graph.add_conditional_edges("validate_recommendation", after_validation)
    graph.add_edge("repair_recommendation", "validate_recommendation")
    graph.add_edge("generate_fallback_copy", "persist_recommendation")
    graph.add_edge("persist_recommendation", END)
    return graph.compile()
