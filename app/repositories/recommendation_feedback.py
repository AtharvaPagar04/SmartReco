from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import RecommendationFeedback, RecommendationItem


FEEDBACK_REASONS = {
    "ALREADY_KNOW": "I already know this",
    "TOO_ADVANCED": "It looks too advanced",
    "TOO_BASIC": "It looks too basic",
    "NOT_INTERESTED_TOPIC": "I’m not interested in this topic",
    "PREFER_MORE_PRACTICAL": "I want something more practical",
    "TOO_EXPENSIVE": "It’s too expensive",
    "NOT_RELEVANT_NOW": "It’s not relevant to my goals right now",
    "OTHER": "Another reason",
}

FEEDBACK_LIFETIME_DAYS = {
    "ALREADY_KNOW": 60,
    "TOO_ADVANCED": 30,
    "TOO_BASIC": 30,
    "NOT_INTERESTED_TOPIC": 45,
    "PREFER_MORE_PRACTICAL": 30,
    "TOO_EXPENSIVE": 30,
    "NOT_RELEVANT_NOW": 14,
    "OTHER": 30,
}


@dataclass(frozen=True)
class FeedbackPreferenceSummary:
    excluded_course_ids: frozenset[str] = frozenset()
    temporary_excluded_course_ids: frozenset[str] = frozenset()
    disliked_categories: dict[str, float] = field(default_factory=dict)
    disliked_tags: dict[str, float] = field(default_factory=dict)
    preferred_difficulty_shift: int = 0
    prefers_practical: bool = False
    price_sensitivity: float = 0.0
    already_known_categories: dict[str, float] = field(default_factory=dict)
    last_reason_code: str | None = None

    def to_profile_dict(self) -> dict:
        return {
            "excluded_course_ids": sorted(self.excluded_course_ids),
            "temporary_excluded_course_ids": sorted(self.temporary_excluded_course_ids),
            "avoid_course_ids": sorted(self.excluded_course_ids),
            "disliked_categories": dict(sorted(self.disliked_categories.items())),
            "disliked_tags": dict(sorted(self.disliked_tags.items())),
            "preferred_difficulty_shift": self.preferred_difficulty_shift,
            "difficulty_preference": {-1: "LOWER", 1: "HIGHER"}.get(self.preferred_difficulty_shift, "UNKNOWN"),
            "prefers_practical": self.prefers_practical,
            "price_sensitivity": round(self.price_sensitivity, 4),
            "already_known_categories": dict(sorted(self.already_known_categories.items())),
            "last_reason_code": self.last_reason_code,
        }


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def record_feedback(
    db: AsyncSession,
    *,
    user_id: str,
    recommendation_item_id: str,
    reason_code: str,
    optional_comment: str | None = None,
) -> RecommendationFeedback:
    reason_code = reason_code.strip().upper()
    if reason_code not in FEEDBACK_REASONS:
        raise ValueError("unknown_feedback_reason")
    if optional_comment is not None and not isinstance(optional_comment, str):
        raise ValueError("feedback_comment_invalid")
    comment = (optional_comment or "").strip() or None
    if comment and len(comment) > 200:
        raise ValueError("feedback_comment_too_long")
    item = await db.scalar(
        select(RecommendationItem)
        .options(selectinload(RecommendationItem.course))
        .where(RecommendationItem.id == recommendation_item_id, RecommendationItem.user_id == user_id)
    )
    if not item:
        raise ValueError("recommendation_item_not_found")
    feedback = await db.scalar(
        select(RecommendationFeedback).where(
            RecommendationFeedback.user_id == user_id,
            RecommendationFeedback.recommendation_item_id == recommendation_item_id,
        )
    )
    now = _now()
    if not feedback:
        feedback = RecommendationFeedback(
            user_id=user_id,
            recommendation_run_id=item.run_id,
            recommendation_item_id=item.id,
            course_id=item.course_id,
            reason_code=reason_code,
            optional_comment=comment,
        )
        db.add(feedback)
    else:
        feedback.reason_code = reason_code
        feedback.optional_comment = comment
        feedback.created_at = now
    item.dismissed_at = item.dismissed_at or now
    await db.flush()
    return feedback


async def feedback_for_user(db: AsyncSession, *, user_id: str, window_days: int = 90) -> list[RecommendationFeedback]:
    cutoff = _now() - timedelta(days=window_days)
    return list((await db.scalars(
        select(RecommendationFeedback)
        .options(selectinload(RecommendationFeedback.course))
        .where(RecommendationFeedback.user_id == user_id, RecommendationFeedback.created_at >= cutoff)
        .order_by(RecommendationFeedback.created_at.desc(), RecommendationFeedback.id.desc())
    )).all())


async def feedback_preferences_for_user(db: AsyncSession, *, user_id: str) -> FeedbackPreferenceSummary:
    rows = await feedback_for_user(db, user_id=user_id)
    now = _now()
    excluded: set[str] = set()
    temporary: set[str] = set()
    categories: dict[str, float] = {}
    tags: dict[str, float] = {}
    known_categories: dict[str, float] = {}
    shift_total = 0.0
    practical = False
    price = 0.0
    last_reason = None
    for feedback in rows:
        age_days = max(0.0, (now - feedback.created_at).total_seconds() / 86400)
        lifetime = FEEDBACK_LIFETIME_DAYS.get(feedback.reason_code, 30)
        if age_days > lifetime:
            continue
        last_reason = last_reason or feedback.reason_code
        strength = max(0.1, 1.0 - age_days / lifetime)
        excluded.add(feedback.course_id)
        if feedback.reason_code == "NOT_RELEVANT_NOW":
            temporary.add(feedback.course_id)
        course = feedback.course
        category = course.category.casefold() if course else ""
        course_tags = [str(tag).casefold() for tag in (course.tags or [])] if course else []
        if feedback.reason_code == "NOT_INTERESTED_TOPIC":
            if category:
                categories[category] = min(1.0, categories.get(category, 0.0) + strength)
            for tag in course_tags[:8]:
                tags[tag] = min(1.0, tags.get(tag, 0.0) + strength)
        elif feedback.reason_code == "ALREADY_KNOW" and category:
            known_categories[category] = min(1.0, known_categories.get(category, 0.0) + strength)
            shift_total += strength
        elif feedback.reason_code == "TOO_ADVANCED":
            shift_total -= strength
        elif feedback.reason_code == "TOO_BASIC":
            shift_total += strength
        elif feedback.reason_code == "PREFER_MORE_PRACTICAL":
            practical = True
        elif feedback.reason_code == "TOO_EXPENSIVE":
            price = min(1.0, price + strength)
    return FeedbackPreferenceSummary(
        excluded_course_ids=frozenset(excluded),
        temporary_excluded_course_ids=frozenset(temporary),
        disliked_categories=categories,
        disliked_tags=tags,
        preferred_difficulty_shift=-1 if shift_total <= -0.5 else 1 if shift_total >= 0.5 else 0,
        prefers_practical=practical,
        price_sensitivity=price,
        already_known_categories=known_categories,
        last_reason_code=last_reason,
    )
