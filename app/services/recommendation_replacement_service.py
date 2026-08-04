from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import RecommendationItem, RecommendationRun
from app.services.recommendation_copy_service import RecommendationOutput, RecommendationOutputItem, deterministic_fallback
from app.services.recommendation_persistence_service import fail_run, persist_run, start_run
from app.services.recommendation_ranking_service import rank_candidates
from app.services.recommendation_retrieval_service import retrieve_candidates


def _candidate_dict(course, *, evidence: dict, score: float = 0.0) -> dict:
    return {
        "course_id": course.id,
        "title": course.title,
        "category": course.category,
        "difficulty": course.difficulty,
        "price": float(course.price),
        "currency": course.currency,
        "tags": list(course.tags or [])[:8],
        "tools_used": list(getattr(course, "tools_used", None) or [])[:6],
        "what_you_will_learn": list(getattr(course, "what_you_will_learn", None) or [])[:4],
        "prerequisites": list(getattr(course, "prerequisites", None) or [])[:3],
        "instructor": course.instructor,
        "duration_minutes": course.duration_minutes,
        "base_personalized_score": score,
        "feedback_adjustment": 0.0,
        "feedback_score": score,
        "deterministic_score": score,
        "semantic_score": None,
        "retrieval_sources": ["feedback_replacement"],
        "evidence": evidence if isinstance(evidence, dict) else {},
    }


def _safe_text(value: str | None, minimum: int, fallback: str) -> str:
    value = (value or "").strip()
    return value if len(value) >= minimum else fallback


async def create_feedback_replacement(db: AsyncSession, user_id: str, item_id: str) -> RecommendationRun | None:
    old_item = await db.scalar(
        select(RecommendationItem)
        .options(selectinload(RecommendationItem.run), selectinload(RecommendationItem.course))
        .where(RecommendationItem.id == item_id, RecommendationItem.user_id == user_id)
    )
    if not old_item:
        return None
    old_run = await db.scalar(
        select(RecommendationRun)
        .options(selectinload(RecommendationRun.items).selectinload(RecommendationItem.course))
        .where(RecommendationRun.id == old_item.run_id)
    )
    if not old_run:
        return None
    run, _, profile_row = await start_run(db, user_id, trigger_type="FEEDBACK_REPLACEMENT", force=True)
    if not run or not profile_row:
        return None
    try:
        profile = dict(profile_row.profile_json or {})
        excluded = set(profile.get("excluded_course_ids", []))
        if old_item.course_id:
            excluded.add(old_item.course_id)
        kept = [
            item for item in sorted(old_run.items, key=lambda current: current.rank)
            if item.id != item_id and not item.dismissed_at and item.course and item.course.is_active and item.course.id not in excluded
        ][:2]
        excluded.update(item.course_id for item in kept)
        profile["excluded_course_ids"] = sorted(excluded)
        needed = max(3 - len(kept), 1)
        candidates, used_semantic, used_sql_fallback = await retrieve_candidates(db, profile, limit=30)
        ranked = rank_candidates(candidates, profile, limit=needed)
        if not ranked:
            await fail_run(db, run.id, "replacement_unavailable", "No replacement candidate was available")
            return None

        preserved_outputs = []
        preserved_candidates = []
        for item in kept:
            evidence = item.evidence_json if isinstance(item.evidence_json, dict) else {}
            evidence_ids = evidence.get("evidence_ids") or [
                entry.get("evidence_id") for entry in evidence.get("evidence", []) if isinstance(entry, dict) and entry.get("evidence_id")
            ]
            preserved_outputs.append(RecommendationOutputItem(
                course_id=item.course_id,
                reason=_safe_text(item.reason, 15, "This course remains a relevant next step in your learning path."),
                how_it_helps=evidence.get("how_it_helps", "This course builds on your current learning path."),
                skill_connection=evidence.get("skill_connection", "Next practical skill"),
                evidence=list(evidence_ids)[:3],
                cta_label=item.cta_label,
            ))
            preserved_candidates.append(_candidate_dict(item.course, evidence=evidence, score=item.deterministic_score))

        replacement_outputs = []
        replacement_candidates = []
        for replacement in ranked[:needed]:
            replacement_cand = _candidate_dict(replacement.course, evidence=replacement.evidence, score=replacement.deterministic_score)
            replacement_cand.update({
                "base_personalized_score": replacement.base_personalized_score,
                "feedback_adjustment": replacement.feedback_adjustment,
                "feedback_score": replacement.feedback_score,
                "semantic_score": replacement.semantic_score,
            })
            fallback = deterministic_fallback(profile, [replacement], 1).recommendations[0]
            replacement_outputs.append(RecommendationOutputItem(
                course_id=fallback.course_id,
                reason=fallback.reason,
                how_it_helps=fallback.how_it_helps,
                skill_connection=fallback.skill_connection,
                evidence=fallback.evidence,
                cta_label=fallback.cta_label,
            ))
            replacement_candidates.append(replacement_cand)

        insertion = min(max(old_item.rank - 1, 0), len(preserved_outputs))
        outputs = preserved_outputs[:insertion] + replacement_outputs + preserved_outputs[insertion:]
        payloads = preserved_candidates[:insertion] + replacement_candidates + preserved_candidates[insertion:]
        output = RecommendationOutput(
            headline=_safe_text(old_run.headline, 4, "A better next step for your learning path"),
            narrative=_safe_text(old_run.narrative, 40, "Your feedback helped us choose a more suitable next step while preserving the recommendations that still fit your learning path."),
            learning_direction=profile.get("learning_direction", "practical learning"),
            recommendations=outputs[:3],
        )
        return await persist_run(db, run.id, output, payloads, used_semantic=used_semantic, used_sql_fallback=used_sql_fallback, used_llm_fallback=True, refinement_count=0, quality="FEEDBACK_REPLACEMENT")
    except Exception as exc:
        await fail_run(db, run.id, "replacement_failed", str(exc))
        return None
