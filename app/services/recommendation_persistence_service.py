from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Course, RecommendationItem, RecommendationRun, RecommendationState, UserInterestProfile
from app.services.interest_profile_service import build_or_refresh_profile
from app.services.recommendation_policy_service import RecommendationDecision, decide, now_utc
from app.services.recommendation_copy_service import RecommendationOutput


_SAFE_ERROR_MESSAGES = {
    "run_interrupted": "Recommendation run was interrupted",
    "recommendation_failed": "Recommendation generation failed",
    "workflow_failed": "Recommendation workflow failed",
    "persistence_failed": "Recommendation result could not be saved",
}


def _safe_error_message(code: str, message: str | None = None) -> str:
    return _SAFE_ERROR_MESSAGES.get(code, "Recommendation generation failed")


def cache_key(
    user_id: str,
    profile_hash: str,
    candidate_ids: list[str],
    *,
    workflow_version: str = "1",
    prompt_version: str = "1",
    model_name: str | None = None,
) -> str:
    model = model_name or settings.mesh_chat_model or "fallback"
    candidate_set_hash = hashlib.sha256(",".join(sorted(candidate_ids)).encode()).hexdigest()
    raw = json.dumps(
        [user_id, profile_hash, str(workflow_version), str(prompt_version), model, candidate_set_hash],
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode()).hexdigest()


async def start_run(db: AsyncSession, user_id: str, *, trigger_type: str = "BEHAVIOR_THRESHOLD", force: bool = False) -> tuple[RecommendationRun | None, RecommendationDecision, UserInterestProfile | None]:
    decision = await decide(db, user_id, trigger_type=trigger_type, force=force)
    if not decision.eligible:
        return None, decision, None
    profile = await build_or_refresh_profile(db, user_id, force=force)
    state = await db.get(RecommendationState, user_id)
    if not state:
        state = RecommendationState(user_id=user_id)
        db.add(state)
        await db.flush()
    now = now_utc()
    if state.active_run_id and state.lease_expires_at and state.lease_expires_at > now:
        return None, RecommendationDecision(False, "RUN_ALREADY_ACTIVE"), profile
    run = RecommendationRun(user_id=user_id, profile_id=profile.id, profile_version=profile.version, profile_hash=profile.profile_hash, trigger_type=trigger_type, status="RUNNING", started_at=now, created_at=now, updated_at=now, model_name=settings.mesh_chat_model or None, embedding_model=settings.mesh_embedding_model)
    db.add(run)
    await db.flush()
    state.active_run_id = run.id
    state.lease_expires_at = now + timedelta(minutes=settings.recommendation_lease_minutes)
    state.last_profiled_event_at = profile.source_event_max_occurred_at
    await db.commit()
    return run, decision, profile


async def persist_run(db: AsyncSession, run_id: str, output: RecommendationOutput, candidates: list[dict], *, used_semantic: bool, used_sql_fallback: bool, used_llm_fallback: bool, refinement_count: int, quality: str, graph_errors: list[dict] | None = None) -> RecommendationRun:
    run = await db.get(RecommendationRun, run_id)
    if not run:
        raise ValueError("Recommendation run not found")
    ids = [item.course_id for item in output.recommendations]
    courses = {course.id: course for course in (await db.scalars(select(Course).where(Course.id.in_(ids), Course.is_active.is_(True)))).all()}
    if len(courses) != len(ids):
        raise ValueError("Recommendation contains an inactive or missing course")
    by_id = {candidate["course_id"]: candidate for candidate in candidates}
    for rank, item in enumerate(output.recommendations, 1):
        candidate = by_id[item.course_id]
        evidence = dict(candidate.get("evidence", {}))
        evidence.update({"how_it_helps": item.how_it_helps, "skill_connection": item.skill_connection, "evidence_ids": item.evidence, "evidence_labels": [entry.get("label") for entry in evidence.get("evidence", []) if isinstance(entry, dict) and entry.get("label")]})
        db.add(RecommendationItem(run_id=run.id, user_id=run.user_id, course_id=item.course_id, rank=rank, deterministic_score=candidate.get("deterministic_score", 0), semantic_score=candidate.get("semantic_score"), agent_selected=not used_llm_fallback, retrieval_sources=candidate.get("retrieval_sources", []), evidence_json=evidence, reason=item.reason, cta_label=item.cta_label))
    run.headline = output.headline
    run.narrative = output.narrative
    run.disclaimer = "Based on your recent course activity."
    run.status = "FALLBACK_SUCCEEDED" if used_llm_fallback else "SUCCEEDED"
    run.candidate_count = len(candidates)
    run.selected_count = len(output.recommendations)
    run.refinement_count = refinement_count
    run.used_semantic_retrieval = used_semantic
    run.used_sql_fallback = used_sql_fallback
    run.used_llm_fallback = used_llm_fallback
    run.completed_at = now_utc()
    if graph_errors:
        error = graph_errors[-1]
        run.error_code = str(error.get("code", "recommendation_fallback"))[:80]
        run.error_message = _safe_error_message(run.error_code, error.get("message"))
    candidate_ids = [candidate["course_id"] for candidate in candidates]
    run.cache_key = cache_key(
        run.user_id,
        run.profile_hash,
        candidate_ids,
        workflow_version=run.workflow_version,
        prompt_version=run.prompt_version,
        model_name=run.model_name,
    )
    state = await db.get(RecommendationState, run.user_id)
    if state and state.active_run_id == run.id:
        state.active_run_id = None
        state.lease_expires_at = None
        state.last_recommendation_at = run.completed_at
        state.last_profile_hash = run.profile_hash
        state.cooldown_until = run.completed_at + timedelta(minutes=settings.recommendation_cooldown_minutes)
        state.dirty_since = None
        state.consecutive_failures = 0
        state.next_retry_at = None
    await db.commit()
    return run



async def fail_run(db: AsyncSession, run_id: str, code: str, message: str) -> None:
    run = await db.get(RecommendationRun, run_id)
    if not run or run.status != "RUNNING":
        return
    run.status = "FAILED"
    run.error_code = code[:80]
    run.error_message = _safe_error_message(code, message)
    run.completed_at = now_utc()
    state = await db.get(RecommendationState, run.user_id)
    if state and state.active_run_id == run_id:
        state.active_run_id = None
        state.lease_expires_at = None
        state.consecutive_failures += 1
        state.next_retry_at = now_utc() + timedelta(minutes=min(60, 2 ** min(state.consecutive_failures, 5)))
    await db.commit()


async def fail_run_in_fresh_session(run_id: str, code: str, message: str) -> None:
    from app import database as app_database

    async with app_database.async_session_maker() as db:
        try:
            await fail_run(db, run_id, code, message)
        except Exception:
            await db.rollback()
            raise
