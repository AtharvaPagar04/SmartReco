import asyncio
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select

from app.config import settings
from app.models import (
    ActivityEvent,
    Course,
    RecommendationDelivery,
    RecommendationItem,
    RecommendationPreference,
    RecommendationRun,
    SessionFollowupState,
    User,
)
from app.services.session_followup_service import (
    build_session_profile_for_agent,
    build_session_snapshot,
    check_session_cooldown,
    check_user_activity_since,
    claim_session_followup,
    find_eligible_sessions,
    get_user_email_preference,
)
from app.jobs.session_followup_job import scan_session_followups
from app.jobs.recommendation_jobs import process_email_deliveries


def _utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


import pytest_asyncio


@pytest_asyncio.fixture
async def sample_courses(db_session):
    c1 = Course(
        title="FastAPI Masterclass",
        slug="fastapi-masterclass",
        short_description="Build async APIs.",
        description="Comprehensive FastAPI guide.",
        category="Backend",
        tags=["python", "fastapi", "async"],
        price=0,
        currency="USD",
        difficulty="INTERMEDIATE",
        instructor="Jane Doe",
        duration_minutes=120,
        is_featured=True,
        is_active=True,
        version=1,
        vector_status="COMPLETED",
    )
    c2 = Course(
        title="Production RAG Systems",
        slug="production-rag-systems",
        short_description="Vector search & LLMs.",
        description="Learn RAG architecture.",
        category="AI / ML",
        tags=["ai", "rag", "qdrant", "python"],
        price=49.99,
        currency="USD",
        difficulty="ADVANCED",
        instructor="John Smith",
        duration_minutes=180,
        is_featured=True,
        is_active=True,
        version=1,
        vector_status="COMPLETED",
    )
    db_session.add_all([c1, c2])
    await db_session.commit()
    await db_session.refresh(c1)
    await db_session.refresh(c2)
    return [c1, c2]


@pytest.mark.asyncio
async def test_session_snapshot_building(db_session, regular_user, sample_courses):
    c1, c2 = sample_courses
    sess_id = "sess_test_snapshot_123"
    now = _utc_now() - timedelta(minutes=20)

    e1 = ActivityEvent(
        event_id="e1",
        user_id=regular_user.id,
        session_id=sess_id,
        event_type="SEARCH",
        search_query="async python API",
        occurred_at=now,
        received_at=now,
    )
    e2 = ActivityEvent(
        event_id="e2",
        user_id=regular_user.id,
        session_id=sess_id,
        event_type="COURSE_VIEW",
        course_id=c1.id,
        occurred_at=now + timedelta(minutes=2),
        received_at=now + timedelta(minutes=2),
    )
    e3 = ActivityEvent(
        event_id="e3",
        user_id=regular_user.id,
        session_id=sess_id,
        event_type="DWELL",
        course_id=c1.id,
        duration_ms=120000,
        occurred_at=now + timedelta(minutes=5),
        received_at=now + timedelta(minutes=5),
    )
    db_session.add_all([e1, e2, e3])
    await db_session.commit()

    snapshot = await build_session_snapshot(db_session, regular_user.id, sess_id)

    assert snapshot.event_count == 3
    assert snapshot.meaningful_event_count == 3
    assert "async python API" in snapshot.search_queries
    assert c1.id in snapshot.viewed_course_ids
    assert snapshot.total_dwell_by_course.get(c1.id) == 120.0
    assert snapshot.session_signal_score > 5.0
    assert "Backend" in snapshot.strongest_categories


@pytest.mark.asyncio
async def test_find_eligible_sessions(db_session, regular_user):
    sess_old = "sess_old_1"
    sess_recent = "sess_recent_1"
    now = _utc_now()

    # Session 1: inactive for 20 minutes (eligible)
    e1 = ActivityEvent(
        event_id="ev_old_1",
        user_id=regular_user.id,
        session_id=sess_old,
        event_type="COURSE_VIEW",
        occurred_at=now - timedelta(minutes=20),
        received_at=now - timedelta(minutes=20),
    )
    # Session 2: active 5 minutes ago (not eligible)
    e2 = ActivityEvent(
        event_id="ev_rec_1",
        user_id=regular_user.id,
        session_id=sess_recent,
        event_type="COURSE_VIEW",
        occurred_at=now - timedelta(minutes=5),
        received_at=now - timedelta(minutes=5),
    )
    db_session.add_all([e1, e2])
    await db_session.commit()

    eligible = await find_eligible_sessions(db_session)
    session_ids = [s.session_id for s in eligible]

    assert sess_old in session_ids
    assert sess_recent not in session_ids


@pytest.mark.asyncio
async def test_claim_session_followup_idempotency(db_session, regular_user):
    sess_id = "sess_claim_test"
    last_act = _utc_now() - timedelta(minutes=20)

    # First claim should succeed
    state1 = await claim_session_followup(
        db_session,
        user_id=regular_user.id,
        session_id=sess_id,
        last_activity_at=last_act,
        event_count=5,
        meaningful_event_count=3,
        signal_score=8.5,
    )
    assert state1 is not None
    assert state1.status == "PROCESSING"

    # Concurrent or second claim should return None
    state2 = await claim_session_followup(
        db_session,
        user_id=regular_user.id,
        session_id=sess_id,
        last_activity_at=last_act,
        event_count=5,
        meaningful_event_count=3,
        signal_score=8.5,
    )
    assert state2 is None


@pytest.mark.asyncio
async def test_user_activity_resumption(db_session, regular_user):
    sess_id = "sess_resumption"
    t1 = _utc_now() - timedelta(minutes=20)
    t2 = _utc_now() - timedelta(minutes=2)

    e1 = ActivityEvent(
        event_id="ev_r1",
        user_id=regular_user.id,
        session_id=sess_id,
        event_type="SEARCH",
        search_query="python",
        occurred_at=t1,
        received_at=t1,
    )
    db_session.add(e1)
    await db_session.commit()

    resumed_before = await check_user_activity_since(db_session, regular_user.id, sess_id, t1)
    assert not resumed_before

    # User resumes activity
    e2 = ActivityEvent(
        event_id="ev_r2",
        user_id=regular_user.id,
        session_id=sess_id,
        event_type="COURSE_CLICK",
        occurred_at=t2,
        received_at=t2,
    )
    db_session.add(e2)
    await db_session.commit()

    resumed_after = await check_user_activity_since(db_session, regular_user.id, sess_id, t1)
    assert resumed_after


@pytest.mark.asyncio
async def test_user_cooldown_check(db_session, regular_user):
    # No previous followup -> no cooldown
    assert not await check_session_cooldown(db_session, regular_user.id)

    # Create a recently completed followup state
    state = SessionFollowupState(
        user_id=regular_user.id,
        session_id="sess_past",
        status="SENT",
        completed_at=_utc_now() - timedelta(hours=2),
    )
    db_session.add(state)
    await db_session.commit()

    # Now in cooldown (since 2h < 6h default)
    assert await check_session_cooldown(db_session, regular_user.id)


@pytest.mark.asyncio
async def test_user_email_preference_auto_provision_and_composite(db_session, regular_user):
    # Without a pre-existing preference row, get_user_email_preference auto-provisions enabled settings
    assert await get_user_email_preference(db_session, regular_user.id) is True

    # Fetch auto-created preference
    pref = await db_session.get(RecommendationPreference, regular_user.id)
    assert pref is not None
    assert pref.recommendations_enabled is True
    assert pref.session_followup_email_enabled is True

    # Turning off recommendations_enabled disables follow-up email
    pref.recommendations_enabled = False
    await db_session.commit()
    assert await get_user_email_preference(db_session, regular_user.id) is False

    # Turning recommendations_enabled back on but session_followup_email_enabled off disables follow-up email
    pref.recommendations_enabled = True
    pref.session_followup_email_enabled = False
    await db_session.commit()
    assert await get_user_email_preference(db_session, regular_user.id) is False

    # Enabling both returns True
    pref.session_followup_email_enabled = True
    await db_session.commit()
    assert await get_user_email_preference(db_session, regular_user.id) is True


@pytest.mark.asyncio
async def test_scan_session_followups_end_to_end(db_session, regular_user, sample_courses, monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "console")
    c1, c2 = sample_courses
    sess_id = "sess_e2e_1"
    now = _utc_now() - timedelta(minutes=25)

    # Enable preference
    pref = RecommendationPreference(
        user_id=regular_user.id,
        session_followup_email_enabled=True,
    )
    db_session.add(pref)

    # Create events with high signal
    e1 = ActivityEvent(
        event_id="e2e_1",
        user_id=regular_user.id,
        session_id=sess_id,
        event_type="SEARCH",
        search_query="FastAPI async backend",
        occurred_at=now,
        received_at=now,
    )
    e2 = ActivityEvent(
        event_id="e2e_2",
        user_id=regular_user.id,
        session_id=sess_id,
        event_type="COURSE_VIEW",
        course_id=c1.id,
        occurred_at=now + timedelta(minutes=2),
        received_at=now + timedelta(minutes=2),
    )
    e3 = ActivityEvent(
        event_id="e2e_3",
        user_id=regular_user.id,
        session_id=sess_id,
        event_type="DWELL",
        course_id=c1.id,
        duration_ms=300000,
        occurred_at=now + timedelta(minutes=5),
        received_at=now + timedelta(minutes=5),
    )
    db_session.add_all([e1, e2, e3])
    await db_session.commit()

    # Run the background job to scan and create delivery
    await scan_session_followups()

    state = await db_session.scalar(
        select(SessionFollowupState).where(
            SessionFollowupState.user_id == regular_user.id,
            SessionFollowupState.session_id == sess_id,
        )
    )
    assert state is not None
    assert state.status == "QUEUED"
    assert state.recommendation_run_id is not None
    assert state.recommendation_delivery_id is not None

    # Now process email deliveries
    await process_email_deliveries()
    await db_session.refresh(state)
    assert state.status == "SENT"
    assert state.completed_at is not None

    # Verify RecommendationRun lineage
    run = await db_session.get(RecommendationRun, state.recommendation_run_id)
    assert run is not None
    assert run.trigger_type == "SESSION_FOLLOWUP"
    assert run.source_session_id == sess_id
    assert run.status in ("SUCCEEDED", "FALLBACK_SUCCEEDED")

    # Verify RecommendationDelivery
    delivery = await db_session.get(RecommendationDelivery, state.recommendation_delivery_id)
    assert delivery is not None
    assert delivery.user_id == regular_user.id
    assert delivery.recipient == regular_user.email
    assert delivery.status == "SENT"


@pytest.mark.asyncio
async def test_recipient_resolution_isolation(db_session, regular_user, admin_user, sample_courses):
    c1, _ = sample_courses
    now = _utc_now() - timedelta(minutes=25)

    # Session for User A (regular_user)
    e_a = ActivityEvent(
        event_id="ev_user_a",
        user_id=regular_user.id,
        session_id="sess_user_a",
        event_type="SEARCH",
        search_query="FastAPI",
        occurred_at=now,
        received_at=now,
    )
    e_a_view = ActivityEvent(
        event_id="ev_user_a_v",
        user_id=regular_user.id,
        session_id="sess_user_a",
        event_type="COURSE_VIEW",
        course_id=c1.id,
        occurred_at=now + timedelta(minutes=1),
        received_at=now + timedelta(minutes=1),
    )

    # Session for User B (admin_user)
    e_b = ActivityEvent(
        event_id="ev_user_b",
        user_id=admin_user.id,
        session_id="sess_user_b",
        event_type="SEARCH",
        search_query="Python ML",
        occurred_at=now,
        received_at=now,
    )
    e_b_view = ActivityEvent(
        event_id="ev_user_b_v",
        user_id=admin_user.id,
        session_id="sess_user_b",
        event_type="COURSE_VIEW",
        course_id=c1.id,
        occurred_at=now + timedelta(minutes=1),
        received_at=now + timedelta(minutes=1),
    )

    db_session.add_all([e_a, e_a_view, e_b, e_b_view])
    await db_session.commit()

    await scan_session_followups()

    deliveries = (await db_session.scalars(select(RecommendationDelivery))).all()
    deliv_a = [d for d in deliveries if d.user_id == regular_user.id]
    deliv_b = [d for d in deliveries if d.user_id == admin_user.id]

    assert len(deliv_a) == 1
    assert deliv_a[0].recipient == regular_user.email
    assert deliv_a[0].recipient != admin_user.email

    assert len(deliv_b) == 1
    assert deliv_b[0].recipient == admin_user.email
    assert deliv_b[0].recipient != regular_user.email


from unittest.mock import patch
import resend


@pytest.mark.asyncio
async def test_creating_delivery_does_not_mark_session_sent(db_session, regular_user, sample_courses):
    c1, _ = sample_courses
    sess_id = "sess_lifecycle_1"
    now = _utc_now() - timedelta(minutes=25)

    pref = RecommendationPreference(user_id=regular_user.id, session_followup_email_enabled=True)
    db_session.add(pref)
    e1 = ActivityEvent(event_id="l1", user_id=regular_user.id, session_id=sess_id, event_type="SEARCH", search_query="FastAPI", occurred_at=now, received_at=now)
    e2 = ActivityEvent(event_id="l2", user_id=regular_user.id, session_id=sess_id, event_type="COURSE_VIEW", course_id=c1.id, occurred_at=now + timedelta(minutes=1), received_at=now + timedelta(minutes=1))
    db_session.add_all([e1, e2])
    await db_session.commit()

    await scan_session_followups()

    state = await db_session.scalar(select(SessionFollowupState).where(SessionFollowupState.user_id == regular_user.id, SessionFollowupState.session_id == sess_id))
    assert state is not None
    assert state.status == "QUEUED"
    assert state.status != "SENT"

    delivery = await db_session.get(RecommendationDelivery, state.recommendation_delivery_id)
    assert delivery is not None
    assert delivery.status == "PENDING"


@pytest.mark.asyncio
async def test_successful_delivery_marks_both_delivery_and_session_sent(db_session, regular_user, sample_courses, monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "console")
    c1, _ = sample_courses
    sess_id = "sess_lifecycle_2"
    now = _utc_now() - timedelta(minutes=25)

    pref = RecommendationPreference(user_id=regular_user.id, session_followup_email_enabled=True)
    db_session.add(pref)
    e1 = ActivityEvent(event_id="l3", user_id=regular_user.id, session_id=sess_id, event_type="SEARCH", search_query="Python ML", occurred_at=now, received_at=now)
    e2 = ActivityEvent(event_id="l4", user_id=regular_user.id, session_id=sess_id, event_type="COURSE_VIEW", course_id=c1.id, occurred_at=now + timedelta(minutes=1), received_at=now + timedelta(minutes=1))
    db_session.add_all([e1, e2])
    await db_session.commit()

    await scan_session_followups()
    state = await db_session.scalar(select(SessionFollowupState).where(SessionFollowupState.user_id == regular_user.id, SessionFollowupState.session_id == sess_id))
    assert state.status == "QUEUED"

    await process_email_deliveries()
    await db_session.refresh(state)
    assert state.status == "SENT"
    assert state.completed_at is not None

    delivery = await db_session.get(RecommendationDelivery, state.recommendation_delivery_id)
    assert delivery.status == "SENT"


@pytest.mark.asyncio
async def test_retryable_provider_failure_leaves_session_unsent(db_session, regular_user, sample_courses, monkeypatch):
    c1, _ = sample_courses
    sess_id = "sess_lifecycle_3"
    now = _utc_now() - timedelta(minutes=25)

    monkeypatch.setattr(settings, "email_provider", "resend")
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key_123")
    monkeypatch.setattr(settings, "email_from_address", "SmartReco <onboarding@resend.dev>")

    pref = RecommendationPreference(user_id=regular_user.id, session_followup_email_enabled=True)
    db_session.add(pref)
    e1 = ActivityEvent(event_id="l5", user_id=regular_user.id, session_id=sess_id, event_type="SEARCH", search_query="Vector DB", occurred_at=now, received_at=now)
    e2 = ActivityEvent(event_id="l6", user_id=regular_user.id, session_id=sess_id, event_type="COURSE_VIEW", course_id=c1.id, occurred_at=now + timedelta(minutes=1), received_at=now + timedelta(minutes=1))
    db_session.add_all([e1, e2])
    await db_session.commit()

    await scan_session_followups()
    state = await db_session.scalar(select(SessionFollowupState).where(SessionFollowupState.user_id == regular_user.id, SessionFollowupState.session_id == sess_id))

    with patch("resend.Emails.send") as mock_send:
        mock_send.side_effect = resend.exceptions.ResendError(code=429, error_type="rate_limit", message="Rate limited", suggested_action="")
        await process_email_deliveries()

    await db_session.refresh(state)
    assert state.status == "QUEUED"
    assert state.status != "SENT"
    assert state.status != "FAILED"

    delivery = await db_session.get(RecommendationDelivery, state.recommendation_delivery_id)
    assert delivery.status == "PENDING"
    assert delivery.attempts == 1


@pytest.mark.asyncio
async def test_permanent_delivery_failure_marks_session_failed(db_session, regular_user, sample_courses, monkeypatch):
    c1, _ = sample_courses
    sess_id = "sess_lifecycle_4"
    now = _utc_now() - timedelta(minutes=25)

    monkeypatch.setattr(settings, "email_provider", "resend")
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key_123")
    monkeypatch.setattr(settings, "email_from_address", "SmartReco <onboarding@resend.dev>")

    pref = RecommendationPreference(user_id=regular_user.id, session_followup_email_enabled=True)
    db_session.add(pref)
    e1 = ActivityEvent(event_id="l7", user_id=regular_user.id, session_id=sess_id, event_type="SEARCH", search_query="RAG Systems", occurred_at=now, received_at=now)
    e2 = ActivityEvent(event_id="l8", user_id=regular_user.id, session_id=sess_id, event_type="COURSE_VIEW", course_id=c1.id, occurred_at=now + timedelta(minutes=1), received_at=now + timedelta(minutes=1))
    db_session.add_all([e1, e2])
    await db_session.commit()

    await scan_session_followups()
    state = await db_session.scalar(select(SessionFollowupState).where(SessionFollowupState.user_id == regular_user.id, SessionFollowupState.session_id == sess_id))

    with patch("resend.Emails.send") as mock_send:
        mock_send.side_effect = resend.exceptions.ResendError(code=401, error_type="invalid_api_key", message="Unauthorized", suggested_action="")
        await process_email_deliveries()

    await db_session.refresh(state)
    assert state.status == "FAILED"
    assert state.completed_at is not None
    assert state.error_code == "email_delivery_failed"

    delivery = await db_session.get(RecommendationDelivery, state.recommendation_delivery_id)
    assert delivery.status == "FAILED"


@pytest.mark.asyncio
async def test_no_second_recommendation_generated_during_retries(db_session, regular_user, sample_courses, monkeypatch):
    c1, _ = sample_courses
    sess_id = "sess_lifecycle_5"
    now = _utc_now() - timedelta(minutes=25)

    monkeypatch.setattr(settings, "email_provider", "resend")
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key_123")
    monkeypatch.setattr(settings, "email_from_address", "SmartReco <onboarding@resend.dev>")

    pref = RecommendationPreference(user_id=regular_user.id, session_followup_email_enabled=True)
    db_session.add(pref)
    e1 = ActivityEvent(event_id="l9", user_id=regular_user.id, session_id=sess_id, event_type="SEARCH", search_query="Async IO", occurred_at=now, received_at=now)
    e2 = ActivityEvent(event_id="l10", user_id=regular_user.id, session_id=sess_id, event_type="COURSE_VIEW", course_id=c1.id, occurred_at=now + timedelta(minutes=1), received_at=now + timedelta(minutes=1))
    db_session.add_all([e1, e2])
    await db_session.commit()

    # Step 1: Initial scan generates recommendation and queues delivery
    await scan_session_followups()
    initial_runs = (await db_session.scalars(select(RecommendationRun).where(RecommendationRun.source_session_id == sess_id))).all()
    assert len(initial_runs) == 1

    # Step 2: Attempt delivery - transient error occurs
    with patch("resend.Emails.send") as mock_send:
        mock_send.side_effect = Exception("Temporary failure")
        await process_email_deliveries()

    # Step 3: Run scan_session_followups again (e.g. background scheduler ticks)
    await scan_session_followups()

    # Step 4: Reset delivery scheduled_for and retry delivery
    state = await db_session.scalar(select(SessionFollowupState).where(SessionFollowupState.user_id == regular_user.id, SessionFollowupState.session_id == sess_id))
    delivery = await db_session.get(RecommendationDelivery, state.recommendation_delivery_id)
    delivery.scheduled_for = _utc_now()
    delivery.next_attempt_at = None
    await db_session.commit()

    with patch("resend.Emails.send") as mock_send:
        mock_send.return_value = {"id": "resend_msg_retry_999"}
        await process_email_deliveries()

    runs_after_retry = (await db_session.scalars(select(RecommendationRun).where(RecommendationRun.source_session_id == sess_id))).all()
    assert len(runs_after_retry) == 1
    assert runs_after_retry[0].id == initial_runs[0].id

    await db_session.refresh(state)
    assert state.status == "SENT"
    await db_session.refresh(delivery)
    assert delivery.status == "SENT"
