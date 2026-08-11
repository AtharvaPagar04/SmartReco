"""
Session Follow-Up Email Job
=============================

Background job called by the APScheduler to:
1. Find sessions eligible for a follow-up recommendation email.
2. For each eligible session: validate signal, prevent duplicates, call the existing
   LangGraph recommendation agent with trigger_type=SESSION_FOLLOWUP, create delivery.

This job does NOT create a new recommendation agent — it reuses the existing
recommendation_service.generate_recommendation() infrastructure with an extended invocation
context. The session snapshot is injected into the LangGraph state via a graph_context dict.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import async_session_maker
from app.models import (
    RecommendationDelivery,
    RecommendationItem,
    RecommendationPreference,
    RecommendationRun,
    SessionFollowupState,
    User,
)
from app.services.recommendation_email_service import email_provider, render_digest
from app.services.session_followup_service import (
    EligibleSession,
    SessionInterestSnapshot,
    build_session_profile_for_agent,
    build_session_retrieval_query,
    build_session_snapshot,
    check_session_cooldown,
    check_user_activity_since,
    claim_session_followup,
    create_session_delivery,
    finish_session_followup,
    find_eligible_sessions,
    get_user_email_preference,
)

logger = logging.getLogger(__name__)

_TRIGGER_TYPE = "SESSION_FOLLOWUP"


async def recover_stale_processing_sessions(db, timeout_minutes: int = 5) -> int:
    """Find SessionFollowupState rows stuck in PROCESSING for longer than timeout_minutes
    without a recommendation_run_id or recommendation_delivery_id, and transition them to FAILED.
    """
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(minutes=timeout_minutes)

    stale_states = (
        await db.scalars(
            select(SessionFollowupState).where(
                SessionFollowupState.status == "PROCESSING",
                SessionFollowupState.updated_at <= cutoff,
                SessionFollowupState.recommendation_run_id.is_(None),
                SessionFollowupState.recommendation_delivery_id.is_(None),
            )
        )
    ).all()

    recovered_count = 0
    for state in stale_states:
        state.status = "FAILED"
        state.error_code = "recommendation_generation_failed"
        state.error_message = "Stale processing timeout recovered"
        state.completed_at = now
        state.updated_at = now
        recovered_count += 1

    if recovered_count > 0:
        await db.commit()
        logger.warning(
            "session_followup.stale_processing_recovered",
            extra={"recovered_count": recovered_count},
        )
    return recovered_count


async def scan_session_followups() -> None:
    """Entry point called by APScheduler every SESSION_FOLLOWUP_SCAN_INTERVAL_SECONDS.

    1. Recover any stale PROCESSING sessions.
    2. Cheap SQL scan to find eligible sessions.
    3. For each: validate, claim, build snapshot, run agent, deliver.
    """
    if not settings.session_followup_enabled:
        return

    logger.info("session_followup.scan.start")

    async with async_session_maker() as db:
        await recover_stale_processing_sessions(db)
        eligible_sessions = await find_eligible_sessions(db)

    logger.info(
        "session_followup.scan.found",
        extra={"eligible_count": len(eligible_sessions)},
    )

    for session in eligible_sessions:
        await _process_eligible_session(session)


async def _process_eligible_session(session: EligibleSession) -> None:
    """Process one eligible session. Uses a fresh DB session for each to isolate failures."""
    user_id = session.user_id
    session_id = session.session_id

    async with async_session_maker() as db:
        try:
            await _run_session_followup(db, session)
        except Exception as exc:
            logger.exception(
                "session_followup.failed",
                extra={
                    "user_id": user_id,
                    "session_id": session_id,
                    "error": str(exc)[:200],
                },
            )
            try:
                await db.rollback()
            except Exception:
                pass

            try:
                state = await db.scalar(
                    select(SessionFollowupState).where(
                        SessionFollowupState.user_id == user_id,
                        SessionFollowupState.session_id == session_id,
                    )
                )
                if state and state.status == "PROCESSING":
                    await finish_session_followup(
                        db,
                        state.id,
                        status="FAILED",
                        error_code="recommendation_generation_failed",
                        error_message=str(exc)[:500],
                    )
            except Exception:
                try:
                    async with async_session_maker() as fresh_db:
                        state = await fresh_db.scalar(
                            select(SessionFollowupState).where(
                                SessionFollowupState.user_id == user_id,
                                SessionFollowupState.session_id == session_id,
                            )
                        )
                        if state and state.status == "PROCESSING":
                            await finish_session_followup(
                                fresh_db,
                                state.id,
                                status="FAILED",
                                error_code="recommendation_generation_failed",
                                error_message=str(exc)[:500],
                            )
                except Exception as inner_exc:
                    logger.error(
                        "session_followup.failure_handler_failed",
                        extra={
                            "user_id": user_id,
                            "session_id": session_id,
                            "error": str(inner_exc)[:200],
                        },
                    )


async def _run_session_followup(db, session: EligibleSession) -> None:
    user_id = session.user_id
    session_id = session.session_id

    # ── 1. Build snapshot & log eligibility ─────────────────────────────────
    snapshot = await build_session_snapshot(db, user_id, session_id)

    logger.info(
        "session_followup.eligible",
        extra={
            "user_id": user_id,
            "session_id": session_id,
            "event_count": snapshot.event_count,
            "meaningful_event_count": snapshot.meaningful_event_count,
            "session_signal_score": snapshot.session_signal_score,
            "last_activity_at": str(session.last_activity_at),
        },
    )

    # ── 2. Check email preference ─────────────────────────────────────────────
    email_enabled = await get_user_email_preference(db, user_id)
    logger.info(
        "session_followup.preference",
        extra={
            "user_id": user_id,
            "session_id": session_id,
            "enabled": email_enabled,
        },
    )
    if not email_enabled:
        logger.info(
            "session_followup.email_disabled",
            extra={"user_id": user_id, "session_id": session_id},
        )
        state = await claim_session_followup(
            db,
            user_id=user_id,
            session_id=session_id,
            last_activity_at=session.last_activity_at,
            event_count=snapshot.event_count,
            meaningful_event_count=snapshot.meaningful_event_count,
            signal_score=snapshot.session_signal_score,
        )
        if state:
            await finish_session_followup(
                db,
                state.id,
                status="SKIPPED_LOW_SIGNAL",
                skip_reason="email_preference_disabled",
            )
        return

    # ── 3. Log snapshot details ───────────────────────────────────────────────
    logger.info(
        "session_followup.snapshot",
        extra={
            "user_id": user_id,
            "session_id": session_id,
            "event_count": snapshot.event_count,
            "meaningful_event_count": snapshot.meaningful_event_count,
            "strongest_categories_count": len(snapshot.strongest_categories),
            "strongest_tags_count": len(snapshot.strongest_tags),
        },
    )

    # ── 4. Check signal threshold ─────────────────────────────────────────────
    if (
        snapshot.session_signal_score < settings.session_followup_min_signal_score
        or snapshot.meaningful_event_count < settings.session_followup_min_meaningful_events
    ):
        logger.info(
            "session_followup.low_signal",
            extra={
                "user_id": user_id,
                "session_id": session_id,
                "signal_score": snapshot.session_signal_score,
                "meaningful_count": snapshot.meaningful_event_count,
            },
        )
        state = await claim_session_followup(
            db,
            user_id=user_id,
            session_id=session_id,
            last_activity_at=session.last_activity_at,
            event_count=snapshot.event_count,
            meaningful_event_count=snapshot.meaningful_event_count,
            signal_score=snapshot.session_signal_score,
        )
        if state:
            await finish_session_followup(
                db,
                state.id,
                status="SKIPPED_LOW_SIGNAL",
                skip_reason="signal_below_threshold",
            )
        return

    # ── 4. Check cooldown (max one session email per user per COOLDOWN_HOURS) ──
    in_cooldown = await check_session_cooldown(db, user_id)
    if in_cooldown:
        logger.info(
            "session_followup.cooldown",
            extra={"user_id": user_id, "session_id": session_id},
        )
        state = await claim_session_followup(
            db,
            user_id=user_id,
            session_id=session_id,
            last_activity_at=session.last_activity_at,
            event_count=snapshot.event_count,
            meaningful_event_count=snapshot.meaningful_event_count,
            signal_score=snapshot.session_signal_score,
        )
        if state:
            await finish_session_followup(
                db,
                state.id,
                status="SKIPPED_COOLDOWN",
                skip_reason="cooldown_active",
            )
        return

    # ── 5. Atomically claim this session ──────────────────────────────────────
    state = await claim_session_followup(
        db,
        user_id=user_id,
        session_id=session_id,
        last_activity_at=session.last_activity_at,
        event_count=snapshot.event_count,
        meaningful_event_count=snapshot.meaningful_event_count,
        signal_score=snapshot.session_signal_score,
    )
    if state is None:
        logger.info(
            "session_followup.already_claimed",
            extra={"user_id": user_id, "session_id": session_id},
        )
        return

    logger.info(
        "session_followup.claimed",
        extra={
            "user_id": user_id,
            "session_id": session_id,
            "state_id": state.id,
        },
    )

    # ── 6. Re-check: did the user resume activity after we started? ───────────
    resumed = await check_user_activity_since(
        db,
        user_id=user_id,
        session_id=session_id,
        since=session.last_activity_at,
    )
    if resumed:
        logger.info(
            "session_followup.user_resumed",
            extra={"user_id": user_id, "session_id": session_id},
        )
        await finish_session_followup(
            db,
            state.id,
            status="SKIPPED_LOW_SIGNAL",
            skip_reason="user_resumed_activity",
        )
        return

    # ── 7. Load user (check email address) ────────────────────────────────────
    user = await db.get(User, user_id)
    if not user or not user.email or not user.is_active:
        await finish_session_followup(
            db,
            state.id,
            status="SKIPPED_LOW_SIGNAL",
            skip_reason="user_invalid_or_no_email",
        )
        return

    # ── 8. Build session-specific profile for the recommendation agent ────────
    # Load long-term profile for exclusions + diversity blending (20-30% weight)
    long_term_profile: dict | None = None
    try:
        from app.services.interest_profile_service import build_or_refresh_profile
        lt_profile_model = await build_or_refresh_profile(db, user_id, force=False)
        long_term_profile = lt_profile_model.profile_json if lt_profile_model else None
    except Exception:
        pass

    session_profile = build_session_profile_for_agent(snapshot, long_term_profile)

    logger.info(
        "session_followup.recommendation.generating",
        extra={
            "user_id": user_id,
            "session_id": session_id,
            "session_confidence": snapshot.session_confidence,
            "top_categories": [c["name"] for c in session_profile.get("top_categories", [])[:2]],
            "top_searches": session_profile.get("top_search_terms", [])[:1],
        },
    )

    state_id = state.id
    # ── 9. Run recommendation agent (reuse existing graph, no new agent) ──────
    run_id: str | None = None
    try:
        run_id, run = await _generate_session_recommendation(
            db,
            user_id=user_id,
            session_id=session_id,
            session_profile=session_profile,
            snapshot=snapshot,
        )
    except Exception as exc:
        logger.exception(
            "session_followup.recommendation.failed",
            extra={"user_id": user_id, "session_id": session_id, "error": str(exc)[:200]},
        )
        try:
            await db.rollback()
        except Exception:
            pass
        try:
            await finish_session_followup(
                db,
                state_id,
                status="FAILED",
                error_code="recommendation_generation_failed",
                error_message=str(exc)[:500],
            )
        except Exception as e1:
            logger.error("finish_session_followup_primary_failed: %s", e1, exc_info=True)
            try:
                async with async_session_maker() as fresh_db:
                    await finish_session_followup(
                        fresh_db,
                        state_id,
                        status="FAILED",
                        error_code="recommendation_generation_failed",
                        error_message=str(exc)[:500],
                    )
            except Exception as e2:
                logger.error("finish_session_followup_fallback_failed: %s", e2, exc_info=True)
        return

    if not run_id:
        await finish_session_followup(
            db,
            state.id,
            status="SKIPPED_NO_RECS",
            skip_reason="no_recommendation_generated",
        )
        return

    logger.info(
        "session_followup.recommendation.generated",
        extra={
            "user_id": user_id,
            "session_id": session_id,
            "recommendation_run_id": run_id,
        },
    )

    # ── 10. Create delivery (persist BEFORE sending — retry delivery separately) ─
    delivery = await create_session_delivery(db, run, user)

    await finish_session_followup(
        db,
        state.id,
        status="QUEUED",
        run_id=run_id,
        delivery_id=delivery.id,
    )

    logger.info(
        "session_followup.delivery.queued",
        extra={
            "user_id": user_id,
            "session_id": session_id,
            "delivery_id": delivery.id,
        },
    )


async def _generate_session_recommendation(
    db,
    user_id: str,
    session_id: str,
    session_profile: dict,
    snapshot: SessionInterestSnapshot,
) -> tuple[str | None, RecommendationRun | None]:
    """
    Invoke the existing LangGraph recommendation graph with a session-specific profile.

    The graph is invoked directly (not through generate_recommendation()) so we can
    inject the session profile dict. We do NOT bypass any existing graph logic —
    we simply pass session_profile as the 'session_profile' context key which the
    graph nodes can use if the trigger_type is SESSION_FOLLOWUP.

    Because the graph currently loads the profile from UserInterestProfile, we need to
    create a temporary in-memory profile that shadows the database one during this run.
    We do this by patching build_or_refresh_profile in the scope of this call only.
    """
    from unittest.mock import patch
    from app.services.interest_profile_service import build_or_refresh_profile
    from app.agents.recommendation_graph import build_recommendation_graph
    from app.services.recommendation_persistence_service import start_run
    from app.services.recommendation_policy_service import RecommendationDecision

    # Build a mock profile object with the session data so start_run can create the run
    from types import SimpleNamespace
    import hashlib, json

    profile_hash = snapshot.profile_hash()
    mock_profile = SimpleNamespace(
        id=None,
        version=1,
        profile_hash=profile_hash,
        profile_json=session_profile,
        source_event_count=snapshot.event_count,
        source_event_max_occurred_at=snapshot.last_activity_at,
        window_started_at=snapshot.started_at or snapshot.last_activity_at,
        window_ended_at=snapshot.last_activity_at,
        generated_at=snapshot.last_activity_at,
    )

    # We bypass the normal start_run eligibility checks (cooldown, threshold) for
    # SESSION_FOLLOWUP — the session_followup_service already enforces them.
    # Create the run record directly.
    from datetime import datetime, timezone, timedelta
    from app.models import RecommendationRun, RecommendationState
    from app.config import settings

    now_ts = datetime.now(timezone.utc).replace(tzinfo=None)
    run = RecommendationRun(
        user_id=user_id,
        profile_id=None,
        profile_version=1,
        profile_hash=profile_hash,
        trigger_type=_TRIGGER_TYPE,
        status="RUNNING",
        started_at=now_ts,
        created_at=now_ts,
        updated_at=now_ts,
        model_name=settings.mesh_chat_model or None,
        embedding_model=settings.mesh_embedding_model,
        source_session_id=session_id,
    )
    db.add(run)
    await db.flush()

    # Build and invoke the graph, passing the session profile as override
    graph = build_recommendation_graph(db)

    try:
        state = await graph.ainvoke({
            "run_id": run.id,
            "user_id": user_id,
            "trigger_type": _TRIGGER_TYPE,
            "session_profile_override": session_profile,
        })
    except Exception as exc:
        run.status = "FAILED"
        run.error_code = "recommendation_failed"
        run.error_message = str(exc)[:500]
        run.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db.commit()
        raise

    # Reload run to get persisted state
    await db.refresh(run)

    if run.status not in ("SUCCEEDED", "FALLBACK_SUCCEEDED"):
        return None, None

    return run.id, run
