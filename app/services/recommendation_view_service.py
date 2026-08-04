from __future__ import annotations

from typing import Any

from app.config import settings
from app.models import RecommendationRun


def build_recommendation_view(
    run: RecommendationRun | None,
    excluded_course_ids: set[str] | None = None,
    action_states: dict[str, Any] | None = None,
    learning_context: dict[str, Any] | None = None,
    pending_replacement: dict[str, Any] | None = None,
    total_eligible_courses: int | None = None,
) -> dict[str, Any] | None:
    if not run:
        return None
    excluded_course_ids = excluded_course_ids or set()
    display_limit = getattr(settings, "recommendation_display_limit", 3)

    items_by_rank: dict[int, Any] = {}
    for item in run.items:
        items_by_rank[item.rank] = item

    active_items: list[dict[str, Any]] = []
    slots: list[dict[str, Any]] = []

    for rank in range(1, display_limit + 1):
        item = items_by_rank.get(rank)
        is_valid = (
            item is not None
            and item.dismissed_at is None
            and item.course is not None
            and item.course.is_active
            and item.course.id not in excluded_course_ids
        )

        if is_valid:
            evidence = item.evidence_json if isinstance(item.evidence_json, dict) else {}
            item_dict: dict[str, Any] = {
                "state": "ACTIVE",
                "item_id": item.id,
                "rank": rank,
                "reason": item.reason,
                "how_it_helps": evidence.get("how_it_helps") or "This course adds a practical next skill to your learning path.",
                "skill_connection": evidence.get("skill_connection") or "Next practical skill",
                "evidence_labels": tuple(evidence.get("evidence_labels") or ()),
                "cta_label": item.cta_label,
                "course": {
                    "id": item.course.id,
                    "slug": item.course.slug,
                    "title": item.course.title,
                    "category": item.course.category,
                    "difficulty": item.course.difficulty,
                    "price": str(item.course.price),
                    "currency": item.course.currency,
                },
                "enrolled": item.course.id in excluded_course_ids,
                "action": (action_states or {}).get(item.course.id),
            }
            item_copy = dict(item_dict)
            item_dict["item"] = item_copy
            active_items.append(item_dict)
            slots.append(item_dict)
        else:
            is_pending = False
            rejected_id = None
            msg = "Your learning path is being refreshed. We’re combining your feedback with your overall learning activity to find a better match."
            state = "REPLACEMENT_PENDING"

            if pending_replacement and (
                pending_replacement.get("rank") == rank
                or (item and pending_replacement.get("rejected_item_id") == item.id)
            ):
                is_pending = True
                rejected_id = pending_replacement.get("rejected_item_id") or (item.id if item else None)
                state = pending_replacement.get("state", "REPLACEMENT_PENDING")
                msg = pending_replacement.get("message", msg)
            elif item is not None or total_eligible_courses is None or total_eligible_courses >= rank:
                is_pending = True
                rejected_id = item.id if item else None
                state = "REPLACEMENT_PENDING"
            else:
                state = "UNAVAILABLE"
                msg = "You’re caught up for now. Continue learning or explore the catalog to unlock more personalized suggestions."

            slot = {
                "state": state,
                "rank": rank,
                "item_id": item.id if item else None,
                "rejected_item_id": rejected_id,
                "message": msg,
                "item": None,
            }
            slots.append(slot)

    context = learning_context or {
        "enrolled": [],
        "completed": [],
        "recently_explored": [],
        "ready_to_start": [],
        "learning_direction": "practical learning",
    }
    return {
        "run_id": run.id,
        "headline": run.headline or "Continue exploring",
        "narrative": run.narrative or "Explore a few courses and SmartReco will use those signals to tailor this section.",
        "generated_at": run.completed_at or run.created_at,
        "is_fallback": run.status == "FALLBACK_SUCCEEDED",
        "items": active_items,
        "recommendations": slots,
        "recommendation_slots": slots,
        "context": context,
        "learning_direction": context.get("learning_direction", "practical learning"),
    }

