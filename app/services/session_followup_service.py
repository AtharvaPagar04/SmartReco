"""
Session Follow-Up Email Service
================================

Responsible for:
1. Scanning ActivityEvent to find sessions eligible for a follow-up recommendation email
   (session inactive for >= SESSION_FOLLOWUP_INACTIVITY_MINUTES).
2. Building a SessionInterestSnapshot: a session-scoped behavioral profile using the
   same event weights as interest_profile_service (no contradictory second weighting model).
3. Converting the snapshot into a LangGraph-compatible profile dict where session intent
   dominates (70-80%) with optional long-term profile support (20-30%).
4. Calling the existing recommendation agent with trigger_type=SESSION_FOLLOWUP.
5. Creating a RecommendationDelivery for the generated run.
6. Enforcing per-session idempotency via SessionFollowupState (unique on user_id+session_id).
7. Enforcing cooldown: max one session follow-up email per user per COOLDOWN_HOURS.

Does NOT create a second recommendation engine.
Does NOT define a second behavioral weighting model.
Uses mesh_chat_service / recommendation_retrieval_service / recommendation_ranking_service as-is.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import (
    ActivityEvent,
    Course,
    RecommendationDelivery,
    RecommendationPreference,
    RecommendationRun,
    SessionFollowupState,
    User,
)
from app.repositories.recommendations import get_or_create_recommendation_preference
from app.services.interest_profile_service import MEANINGFUL_EVENTS, _decay, _to_naive

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ── Meaningful event weights (identical to interest_profile_service to avoid drift) ──────────────
_EVENT_WEIGHTS: dict[str, float] = {
    "RECOMMENDATION_CLICK": 5.0,
    "SEARCH": 5.0,
    "COURSE_CLICK": 4.0,
    "COURSE_VIEW": 3.0,
    "DWELL": 0.0,          # DWELL is weighted dynamically by duration_ms below
    "COURSE_IMPRESSION": 0.5,
    "FILTER_CHANGE": 0.5,
    "PAGE_VIEW": 0.1,
}

# Events that constitute meaningful intent for session follow-up eligibility
SESSION_MEANINGFUL_EVENTS = {
    "RECOMMENDATION_CLICK", "COURSE_CLICK", "COURSE_VIEW", "DWELL",
    "SEARCH", "FILTER_CHANGE",
}

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.-]*", re.I)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalize_dt(dt: datetime | None) -> datetime | None:
    return _to_naive(dt)


# ── SessionInterestSnapshot ───────────────────────────────────────────────────────────────────────

@dataclass
class SessionInterestSnapshot:
    """Behavioral profile derived strictly from one session (user_id + session_id)."""

    user_id: str
    session_id: str
    started_at: datetime | None
    last_activity_at: datetime | None

    event_count: int = 0
    meaningful_event_count: int = 0

    viewed_course_ids: list[str] = field(default_factory=list)
    clicked_course_ids: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)

    category_affinity: dict[str, float] = field(default_factory=dict)
    tag_affinity: dict[str, float] = field(default_factory=dict)

    # course_id -> total dwell in seconds
    total_dwell_by_course: dict[str, float] = field(default_factory=dict)

    # Ordered by signal strength, strongest first
    strongest_course_ids: list[str] = field(default_factory=list)
    strongest_categories: list[str] = field(default_factory=list)
    strongest_tags: list[str] = field(default_factory=list)

    session_confidence: float = 0.0
    session_signal_score: float = 0.0

    def profile_hash(self) -> str:
        canonical = json.dumps(
            {
                "session_id": self.session_id,
                "viewed": sorted(self.viewed_course_ids),
                "clicked": sorted(self.clicked_course_ids),
                "searches": sorted(self.search_queries),
                "categories": sorted(self.category_affinity.keys()),
                "tags": sorted(self.tag_affinity.keys()),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode()).hexdigest()


async def build_session_snapshot(
    db: AsyncSession,
    user_id: str,
    session_id: str,
) -> SessionInterestSnapshot:
    """Build a SessionInterestSnapshot using only events for user_id+session_id.

    Uses the same decay and action weights as interest_profile_service to maintain
    a single behavioral model. Session intent is NOT diluted by global history here.
    """
    now = _now_utc()

    events = list(
        (
            await db.execute(
                select(ActivityEvent, Course)
                .outerjoin(Course, Course.id == ActivityEvent.course_id)
                .where(
                    ActivityEvent.user_id == user_id,
                    ActivityEvent.session_id == session_id,
                )
                .order_by(ActivityEvent.occurred_at.asc())
            )
        ).all()
    )

    snapshot = SessionInterestSnapshot(
        user_id=user_id,
        session_id=session_id,
        started_at=events[0][0].occurred_at if events else None,
        last_activity_at=events[-1][0].occurred_at if events else None,
    )

    snapshot.event_count = len(events)

    category_scores: dict[str, float] = {}
    tag_scores: dict[str, float] = {}
    course_scores: dict[str, float] = {}
    course_dwell: dict[str, float] = {}
    viewed_set: set[str] = set()
    clicked_set: set[str] = set()
    search_set: dict[str, str] = {}  # normalized -> original
    total_signal = 0.0

    for event, course in events:
        decay = _decay(event.occurred_at, now)
        etype = event.event_type

        if etype in SESSION_MEANINGFUL_EVENTS:
            snapshot.meaningful_event_count += 1

        if etype == "DWELL":
            duration_s = min(max((event.duration_ms or 0) / 1000, 0), 1800)
            dwell_weight = min(8.0, max(0.0, duration_s / 30))
            raw_score = dwell_weight * decay
            if course and duration_s >= 5:
                course_dwell[course.id] = course_dwell.get(course.id, 0) + duration_s
                _merge(course_scores, course.id, raw_score)
            total_signal += raw_score
            if course:
                _merge(category_scores, course.category, raw_score)
                for tag in course.tags or []:
                    _merge(tag_scores, str(tag), raw_score * 0.5)

        elif etype == "SEARCH":
            q = (event.search_query or "").strip()
            if len(q) >= 2:
                nq = q.casefold()
                if nq not in search_set:
                    search_set[nq] = q
                raw_score = 5.0 * decay
                total_signal += raw_score
                # Reinforce categories matching search text
                for cat in list(category_scores):
                    if cat.casefold() in nq:
                        category_scores[cat] += 2.0 * decay

        elif etype in ("COURSE_VIEW", "COURSE_CLICK", "RECOMMENDATION_CLICK"):
            weight = _EVENT_WEIGHTS.get(etype, 1.0)
            raw_score = weight * decay
            total_signal += raw_score
            if etype == "COURSE_VIEW" and course:
                viewed_set.add(course.id)
            if etype in ("COURSE_CLICK", "RECOMMENDATION_CLICK") and course:
                clicked_set.add(course.id)
            if course:
                _merge(course_scores, course.id, raw_score)
                _merge(category_scores, course.category, raw_score)
                for tag in course.tags or []:
                    _merge(tag_scores, str(tag), raw_score * 0.5)

        elif etype in ("FILTER_CHANGE", "COURSE_IMPRESSION"):
            weight = _EVENT_WEIGHTS.get(etype, 0.5)
            raw_score = weight * decay
            total_signal += raw_score
            if course:
                _merge(category_scores, course.category, raw_score * 0.3)

    # Normalise and sort
    snapshot.viewed_course_ids = list(viewed_set)
    snapshot.clicked_course_ids = list(clicked_set)
    snapshot.search_queries = list(search_set.values())[:8]
    snapshot.total_dwell_by_course = course_dwell
    snapshot.category_affinity = category_scores
    snapshot.tag_affinity = tag_scores
    snapshot.session_signal_score = round(total_signal, 4)

    # Top courses by signal strength
    snapshot.strongest_course_ids = [
        cid for cid, _ in sorted(course_scores.items(), key=lambda x: -x[1])
    ][:5]
    snapshot.strongest_categories = [
        cat for cat, _ in sorted(category_scores.items(), key=lambda x: -x[1])
    ][:4]
    snapshot.strongest_tags = [
        tag for tag, _ in sorted(tag_scores.items(), key=lambda x: -x[1])
    ][:6]

    # Confidence: parallels interest_profile_service confidence formula but session-scoped
    searches = len(search_set)
    course_interactions = len(viewed_set | clicked_set)
    dwell_total = sum(course_dwell.values())
    snapshot.session_confidence = round(
        min(
            1.0,
            0.15 * min(4, snapshot.meaningful_event_count)
            + 0.10 * min(3, course_interactions)
            + 0.10 * min(2, searches)
            + (0.20 if dwell_total >= 30 else 0),
        ),
        4,
    )

    return snapshot


def _merge(d: dict[str, float], key: str, score: float) -> None:
    if not key:
        return
    d[key] = d.get(key, 0.0) + score


def build_session_profile_for_agent(
    snapshot: SessionInterestSnapshot,
    long_term_profile: dict | None = None,
) -> dict:
    """Build an agent-compatible profile dict with session intent dominating (70-80%).

    The profile shape matches what recommendation_retrieval_service.build_retrieval_query
    and recommendation_ranking_service.rank_candidates expect.

    Long-term profile is optionally blended in at 20-30% weight for diversity signals.
    """
    # ── Session-derived categories (normalised 0-1) ─────────────────────────────
    max_cat = max(snapshot.category_affinity.values(), default=1.0) or 1.0
    session_categories = [
        {"name": cat, "score": round(score / max_cat, 4)}
        for cat, score in sorted(snapshot.category_affinity.items(), key=lambda x: -x[1])
    ][:5]

    # ── Session-derived tags ─────────────────────────────────────────────────────
    max_tag = max(snapshot.tag_affinity.values(), default=1.0) or 1.0
    session_tags = [
        {"name": tag, "score": round(score / max_tag, 4)}
        for tag, score in sorted(snapshot.tag_affinity.items(), key=lambda x: -x[1])
    ][:8]

    # ── Session search terms ─────────────────────────────────────────────────────
    session_searches = [
        {"term": q, "score": 1.0, "searched_at": (snapshot.last_activity_at or _now_utc()).isoformat()}
        for q in snapshot.search_queries[:4]
    ]

    # ── Blend with long-term profile (20-30% weight) if available ─────────────
    if long_term_profile and long_term_profile.get("confidence", 0) > 0.1:
        lt_cats = {
            item["name"]: item["score"] * 0.25
            for item in long_term_profile.get("top_categories", [])[:4]
        }
        lt_tags = {
            item["name"]: item["score"] * 0.20
            for item in long_term_profile.get("top_tags", [])[:6]
        }
        # Merge: session score (1.0 weight) + long-term score (0.25 weight), re-normalise
        blended_cats: dict[str, float] = {}
        for item in session_categories:
            blended_cats[item["name"]] = item["score"] * 0.75 + lt_cats.get(item["name"], 0)
        for name, score in lt_cats.items():
            if name not in blended_cats:
                blended_cats[name] = score
        if blended_cats:
            max_b = max(blended_cats.values()) or 1.0
            session_categories = [
                {"name": n, "score": round(s / max_b, 4)}
                for n, s in sorted(blended_cats.items(), key=lambda x: -x[1])
            ][:5]

        blended_tags: dict[str, float] = {}
        for item in session_tags:
            blended_tags[item["name"]] = item["score"] * 0.80 + lt_tags.get(item["name"], 0)
        for name, score in lt_tags.items():
            if name not in blended_tags:
                blended_tags[name] = score
        if blended_tags:
            max_t = max(blended_tags.values()) or 1.0
            session_tags = [
                {"name": n, "score": round(s / max_t, 4)}
                for n, s in sorted(blended_tags.items(), key=lambda x: -x[1])
            ][:8]

        # Merge search terms (de-dup by normalised term)
        seen_terms: set[str] = {item["term"].casefold() for item in session_searches}
        for item in long_term_profile.get("top_search_terms", [])[:2]:
            if item["term"].casefold() not in seen_terms:
                session_searches.append({"term": item["term"], "score": 0.25, "searched_at": item.get("searched_at", "")})
                seen_terms.add(item["term"].casefold())

    # ── Pull exclusions from long-term profile ──────────────────────────────────
    excluded: list[str] = list(long_term_profile.get("excluded_course_ids", [])[:30] if long_term_profile else [])
    completed_ids: list[str] = list(long_term_profile.get("completed_course_ids", []) if long_term_profile else [])
    enrolled_ids: list[str] = list(long_term_profile.get("enrolled_course_ids", []) if long_term_profile else [])
    dismissed_ids: list[str] = list(long_term_profile.get("dismissed_course_ids", []) if long_term_profile else [])
    purchased_ids: list[str] = list(long_term_profile.get("purchased_unstarted_course_ids", []) if long_term_profile else [])

    # Build evidence for viewed/clicked courses during session (used by ranking)
    session_viewed_summary = []
    for course_id in snapshot.strongest_course_ids[:3]:
        session_viewed_summary.append({"course_id": course_id, "title": "", "category": "", "difficulty": "BEGINNER", "tags": []})

    session_hint = {
        "session_id": snapshot.session_id,
        "session_viewed_course_ids": snapshot.viewed_course_ids[:10],
        "session_clicked_course_ids": snapshot.clicked_course_ids[:10],
        "session_search_queries": snapshot.search_queries[:4],
        "session_dwell_seconds": int(sum(snapshot.total_dwell_by_course.values())),
        "session_confidence": snapshot.session_confidence,
    }

    profile = {
        "profile_version": 1,
        "top_categories": session_categories,
        "top_tags": session_tags,
        "top_search_terms": session_searches,
        "engaged_course_ids": snapshot.strongest_course_ids[:8],
        "recent_course_ids": (snapshot.viewed_course_ids + snapshot.clicked_course_ids)[:8],
        # Exclusions from long-term profile only (session views remain eligible)
        "excluded_course_ids": excluded,
        "completed_course_ids": completed_ids,
        "enrolled_course_ids": enrolled_ids,
        "purchased_unstarted_course_ids": purchased_ids,
        "recently_viewed_course_ids": snapshot.viewed_course_ids[:20],
        "continued_course_ids": [],
        "dismissed_course_ids": dismissed_ids,
        "recommendation_feedback": long_term_profile.get("recommendation_feedback", {}) if long_term_profile else {},
        "completed_courses": long_term_profile.get("completed_courses", []) if long_term_profile else [],
        "enrolled_courses": long_term_profile.get("enrolled_courses", []) if long_term_profile else [],
        "recently_viewed_courses": session_viewed_summary,
        "signal_summary": {
            "searches": len(snapshot.search_queries),
            "course_clicks": len(snapshot.clicked_course_ids),
            "course_views": len(snapshot.viewed_course_ids),
            "qualified_impressions": 0,
            "dwell_seconds": int(sum(snapshot.total_dwell_by_course.values())),
        },
        "confidence": snapshot.session_confidence,
        "distinct_sessions": 1,
        "session_hint": session_hint,
    }

    return profile


def build_session_retrieval_query(snapshot: SessionInterestSnapshot) -> str:
    """Build a semantic retrieval query that reflects THIS session's strongest signals."""
    parts: list[str] = []

    if snapshot.search_queries:
        parts.append("User searched for: " + ", ".join(snapshot.search_queries[:3]))

    if snapshot.strongest_categories:
        parts.append("Primary interest in: " + ", ".join(snapshot.strongest_categories[:3]))

    if snapshot.strongest_tags:
        parts.append("Key topics: " + ", ".join(snapshot.strongest_tags[:5]))

    if snapshot.total_dwell_by_course:
        # The most dwelled courses are the strongest intent signal
        top_dwell = sorted(snapshot.total_dwell_by_course.items(), key=lambda x: -x[1])[:2]
        ids = [cid for cid, _ in top_dwell]
        if ids:
            parts.append(f"Deep engagement with {len(ids)} course(s) in this session")

    if not parts:
        cats = snapshot.strongest_categories[:2] or ["practical learning"]
        parts.append("Interested in " + ", ".join(cats))

    return ". ".join(parts)


# ── Eligibility scanning ──────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class EligibleSession:
    user_id: str
    session_id: str
    last_activity_at: datetime
    event_count: int
    meaningful_event_count: int


async def find_eligible_sessions(db: AsyncSession, *, batch_size: int = 20) -> list[EligibleSession]:
    """Find (user_id, session_id) pairs whose last meaningful activity is older than
    the inactivity window AND that have not already been processed.

    Returns cheap SQL aggregates only — no snapshots are built here.
    """
    import sqlalchemy as sa

    cutoff = _now_utc() - timedelta(minutes=settings.session_followup_inactivity_minutes)

    meaningful_case = sa.case(
        (ActivityEvent.event_type.in_(SESSION_MEANINGFUL_EVENTS), 1),
        else_=0,
    )

    stmt = (
        select(
            ActivityEvent.user_id,
            ActivityEvent.session_id,
            func.max(ActivityEvent.occurred_at).label("last_at"),
            func.count(ActivityEvent.id).label("event_count"),
            func.sum(meaningful_case).label("meaningful_count"),
        )
        .where(
            ActivityEvent.user_id.is_not(None),
            ActivityEvent.event_type.in_(SESSION_MEANINGFUL_EVENTS | {"PAGE_VIEW"}),
        )
        .group_by(ActivityEvent.user_id, ActivityEvent.session_id)
        .having(func.max(ActivityEvent.occurred_at) <= cutoff)
        .order_by(func.max(ActivityEvent.occurred_at))
        .limit(batch_size * 3)  # fetch extras to account for already-processed ones
    )

    rows = (await db.execute(stmt)).all()

    eligible: list[EligibleSession] = []
    for row in rows:
        # Skip if SessionFollowupState already exists (any terminal status)
        existing_status = await db.scalar(
            select(SessionFollowupState.status).where(
                SessionFollowupState.user_id == row.user_id,
                SessionFollowupState.session_id == row.session_id,
            )
        )
        if existing_status in {"PROCESSING", "QUEUED", "DELIVERY_PENDING", "SENT", "SKIPPED_LOW_SIGNAL", "SKIPPED_NO_RECS", "SKIPPED_COOLDOWN", "FAILED"}:
            continue

        last_at = _normalize_dt(row.last_at) or _now_utc()
        eligible.append(
            EligibleSession(
                user_id=row.user_id,
                session_id=row.session_id,
                last_activity_at=last_at,
                event_count=int(row.event_count or 0),
                meaningful_event_count=int(row.meaningful_count or 0),
            )
        )
        if len(eligible) >= batch_size:
            break

    return eligible


async def claim_session_followup(
    db: AsyncSession,
    user_id: str,
    session_id: str,
    last_activity_at: datetime,
    event_count: int,
    meaningful_event_count: int,
    signal_score: float,
) -> SessionFollowupState | None:
    """Atomically create-or-skip a SessionFollowupState row for this session.

    Uses INSERT-or-skip semantics to prevent concurrent duplicate processing.
    Returns the row if we successfully claimed it (status=PROCESSING), else None.
    """
    now = _now_utc()
    eligible_at = last_activity_at + timedelta(minutes=settings.session_followup_inactivity_minutes)

    # Check if already exists
    existing = await db.scalar(
        select(SessionFollowupState).where(
            SessionFollowupState.user_id == user_id,
            SessionFollowupState.session_id == session_id,
        )
    )
    if existing:
        if existing.status not in ("PENDING",):
            return None
        # Claim it
        existing.status = "PROCESSING"
        existing.processing_started_at = now
        existing.session_signal_score = signal_score
        existing.event_count = event_count
        existing.meaningful_event_count = meaningful_event_count
        try:
            await db.commit()
            await db.refresh(existing)
            return existing
        except Exception:
            await db.rollback()
            return None

    # Insert fresh
    row = SessionFollowupState(
        user_id=user_id,
        session_id=session_id,
        last_activity_at=last_activity_at,
        eligible_at=eligible_at,
        status="PROCESSING",
        processing_started_at=now,
        event_count=event_count,
        meaningful_event_count=meaningful_event_count,
        session_signal_score=signal_score,
    )
    db.add(row)
    try:
        await db.commit()
        await db.refresh(row)
        return row
    except IntegrityError:
        # Another worker already inserted — safe to skip
        await db.rollback()
        return None


async def check_user_activity_since(
    db: AsyncSession,
    user_id: str,
    session_id: str,
    since: datetime,
) -> bool:
    """Return True if new activity arrived for this session AFTER 'since' (user resumed)."""
    later_event = await db.scalar(
        select(ActivityEvent.id).where(
            ActivityEvent.user_id == user_id,
            ActivityEvent.session_id == session_id,
            ActivityEvent.occurred_at > since,
        ).limit(1)
    )
    return later_event is not None


async def check_session_cooldown(
    db: AsyncSession,
    user_id: str,
) -> bool:
    """Return True if the user already received a session follow-up email within the cooldown window."""
    cooldown_cutoff = _now_utc() - timedelta(hours=settings.session_followup_cooldown_hours)
    recent_sent = await db.scalar(
        select(SessionFollowupState.id).where(
            SessionFollowupState.user_id == user_id,
            SessionFollowupState.status == "SENT",
            SessionFollowupState.completed_at >= cooldown_cutoff,
        ).limit(1)
    )
    return recent_sent is not None


async def get_user_email_preference(
    db: AsyncSession,
    user_id: str,
) -> bool:
    """Return True if user has opted in to recommendations AND session follow-up emails.

    Uses get_or_create_recommendation_preference so legacy users automatically get preferences.
    Requires BOTH recommendations_enabled AND session_followup_email_enabled to be True.
    """
    pref = await get_or_create_recommendation_preference(db, user_id)
    return bool(pref.recommendations_enabled and pref.session_followup_email_enabled)


async def finish_session_followup(
    db: AsyncSession,
    state_id: str,
    *,
    status: str,
    run_id: str | None = None,
    delivery_id: str | None = None,
    skip_reason: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    """Mark the SessionFollowupState as terminal."""
    state = await db.get(SessionFollowupState, state_id)
    if not state:
        return
    state.status = status
    if status in ("SENT", "FAILED", "SKIPPED_LOW_SIGNAL", "SKIPPED_NO_RECS", "SKIPPED_COOLDOWN"):
        state.completed_at = _now_utc()
    if run_id:
        state.recommendation_run_id = run_id
    if delivery_id:
        state.recommendation_delivery_id = delivery_id
    if skip_reason:
        state.skip_reason = skip_reason[:80]
    if error_code:
        state.error_code = error_code[:80]
    if error_message:
        state.error_message = str(error_message)[:500]
    await db.commit()


async def create_session_delivery(
    db: AsyncSession,
    run: RecommendationRun,
    user: User,
) -> RecommendationDelivery:
    """Create a RecommendationDelivery for this session follow-up run."""
    now = _now_utc()
    delivery = RecommendationDelivery(
        run_id=run.id,
        user_id=user.id,
        recipient=user.email,
        scheduled_for=now,
        status="PENDING",
    )
    db.add(delivery)
    await db.commit()
    await db.refresh(delivery)
    return delivery
