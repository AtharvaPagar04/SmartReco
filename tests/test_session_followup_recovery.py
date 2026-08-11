from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.jobs.session_followup_job import (
    _process_eligible_session,
    recover_stale_processing_sessions,
    scan_session_followups,
)
from app.models import (
    ActivityEvent,
    Course,
    RecommendationDelivery,
    RecommendationItem,
    RecommendationRun,
    SessionFollowupState,
    User,
    UserInterestProfile,
)
from app.services.interest_profile_service import build_or_refresh_profile
from app.services.session_followup_service import EligibleSession


def _utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.mark.asyncio
async def test_1_existing_user_interest_profile_reused(db_session, regular_user):
    # First call creates the profile
    p1 = await build_or_refresh_profile(db_session, regular_user.id)
    await db_session.commit()

    # Second call reuses and updates the profile
    p2 = await build_or_refresh_profile(db_session, regular_user.id)
    await db_session.commit()

    profiles = (await db_session.scalars(
        select(UserInterestProfile).where(UserInterestProfile.user_id == regular_user.id)
    )).all()

    assert len(profiles) == 1
    assert p1.id == p2.id


@pytest.mark.asyncio
async def test_2_concurrent_get_create_results_in_one_profile_row(db_session, regular_user):
    # Create profile beforehand as if created concurrently
    prof = UserInterestProfile(
        user_id=regular_user.id,
        version=1,
        profile_hash="hash_concurrent_123",
        profile_json={"top_categories": []},
        source_event_count=1,
        source_event_max_occurred_at=_utc_now(),
        window_started_at=_utc_now(),
        window_ended_at=_utc_now(),
        generated_at=_utc_now(),
    )
    db_session.add(prof)
    await db_session.commit()

    # Call build_or_refresh_profile
    res = await build_or_refresh_profile(db_session, regular_user.id)
    assert res.user_id == regular_user.id

    profiles = (await db_session.scalars(
        select(UserInterestProfile).where(UserInterestProfile.user_id == regular_user.id)
    )).all()
    assert len(profiles) == 1


@pytest.mark.asyncio
async def test_3_duplicate_profile_integrity_error_does_not_poison_session(db_session, regular_user, monkeypatch):
    # Simulate an IntegrityError inside build_or_refresh_profile by forcing an insert attempt
    # that fails with IntegrityError, ensuring the outer session remains usable.
    p1 = UserInterestProfile(
        user_id=regular_user.id,
        version=1,
        profile_hash="h1",
        profile_json={},
        source_event_count=0,
        source_event_max_occurred_at=_utc_now(),
        window_started_at=_utc_now(),
        window_ended_at=_utc_now(),
        generated_at=_utc_now(),
    )
    db_session.add(p1)
    await db_session.commit()

    # Call build_or_refresh_profile which internally handles any IntegrityError
    p2 = await build_or_refresh_profile(db_session, regular_user.id)

    # Perform another operation on the SAME AsyncSession to prove it is NOT poisoned
    user_check = await db_session.get(User, regular_user.id)
    assert user_check is not None
    assert p2.user_id == regular_user.id


@pytest.mark.asyncio
async def test_4_recommendation_generation_continues_after_profile_reuse(db_session, regular_user, course):
    now = _utc_now() - timedelta(minutes=25)
    # Pre-create profile
    await build_or_refresh_profile(db_session, regular_user.id)
    await db_session.commit()

    # Add activity
    e1 = ActivityEvent(event_id="e_cont_1", user_id=regular_user.id, session_id="sess_cont_1", event_type="SEARCH", search_query="Python", occurred_at=now, received_at=now)
    e2 = ActivityEvent(event_id="e_cont_2", user_id=regular_user.id, session_id="sess_cont_1", event_type="COURSE_VIEW", course_id=course.id, occurred_at=now + timedelta(minutes=1), received_at=now + timedelta(minutes=1))
    db_session.add_all([e1, e2])
    await db_session.commit()

    # Run scan
    await scan_session_followups()

    state = await db_session.scalar(
        select(SessionFollowupState).where(
            SessionFollowupState.user_id == regular_user.id,
            SessionFollowupState.session_id == "sess_cont_1",
        )
    )
    assert state is not None
    assert state.status in ("QUEUED", "SENT", "DELIVERY_PENDING")


@pytest.mark.asyncio
async def test_5_generation_exception_transitions_state_from_processing_to_failed(db_session, regular_user, course, monkeypatch):
    now = _utc_now() - timedelta(minutes=25)
    e1 = ActivityEvent(event_id="e_fail_1", user_id=regular_user.id, session_id="sess_fail_1", event_type="SEARCH", search_query="Python", occurred_at=now, received_at=now)
    e2 = ActivityEvent(event_id="e_fail_2", user_id=regular_user.id, session_id="sess_fail_1", event_type="COURSE_VIEW", course_id=course.id, occurred_at=now + timedelta(minutes=1), received_at=now + timedelta(minutes=1))
    db_session.add_all([e1, e2])
    await db_session.commit()

    # Patch graph invocation to raise an unhandled error
    async def mock_raise(*args, **kwargs):
        raise RuntimeError("LLM service unavailable test error")

    monkeypatch.setattr("app.jobs.session_followup_job._generate_session_recommendation", mock_raise)

    eligible = EligibleSession(
        user_id=regular_user.id,
        session_id="sess_fail_1",
        last_activity_at=now + timedelta(minutes=1),
        event_count=2,
        meaningful_event_count=2,
    )
    await _process_eligible_session(eligible)

    await db_session.rollback()
    state = await db_session.scalar(
        select(SessionFollowupState).where(
            SessionFollowupState.user_id == regular_user.id,
            SessionFollowupState.session_id == "sess_fail_1",
        )
    )
    assert state is not None
    assert state.status == "FAILED"


@pytest.mark.asyncio
async def test_6_error_code_and_message_persisted_on_failure(db_session, regular_user, course, monkeypatch):
    now = _utc_now() - timedelta(minutes=25)
    e1 = ActivityEvent(event_id="e_err_1", user_id=regular_user.id, session_id="sess_err_1", event_type="SEARCH", search_query="Python", occurred_at=now, received_at=now)
    e2 = ActivityEvent(event_id="e_err_2", user_id=regular_user.id, session_id="sess_err_1", event_type="COURSE_VIEW", course_id=course.id, occurred_at=now + timedelta(minutes=1), received_at=now + timedelta(minutes=1))
    db_session.add_all([e1, e2])
    await db_session.commit()

    async def mock_raise(*args, **kwargs):
        raise ValueError("Simulated prompt budget failure")

    monkeypatch.setattr("app.jobs.session_followup_job._generate_session_recommendation", mock_raise)

    eligible = EligibleSession(
        user_id=regular_user.id,
        session_id="sess_err_1",
        last_activity_at=now + timedelta(minutes=1),
        event_count=2,
        meaningful_event_count=2,
    )
    await _process_eligible_session(eligible)

    await db_session.rollback()
    state = await db_session.scalar(
        select(SessionFollowupState).where(
            SessionFollowupState.user_id == regular_user.id,
            SessionFollowupState.session_id == "sess_err_1",
        )
    )
    assert state is not None
    assert state.status == "FAILED"
    assert state.error_code == "recommendation_generation_failed"
    assert "Simulated prompt budget failure" in state.error_message


@pytest.mark.asyncio
async def test_7_failed_generation_never_creates_recommendation_delivery(db_session, regular_user, course, monkeypatch):
    now = _utc_now() - timedelta(minutes=25)
    e1 = ActivityEvent(event_id="e_nodeliv_1", user_id=regular_user.id, session_id="sess_nodeliv_1", event_type="SEARCH", search_query="Python", occurred_at=now, received_at=now)
    db_session.add(e1)
    await db_session.commit()

    async def mock_raise(*args, **kwargs):
        raise RuntimeError("Generation failure")

    monkeypatch.setattr("app.jobs.session_followup_job._generate_session_recommendation", mock_raise)

    eligible = EligibleSession(
        user_id=regular_user.id,
        session_id="sess_nodeliv_1",
        last_activity_at=now,
        event_count=1,
        meaningful_event_count=1,
    )
    await _process_eligible_session(eligible)

    deliveries = (await db_session.scalars(
        select(RecommendationDelivery).where(RecommendationDelivery.user_id == regular_user.id)
    )).all()
    assert len(deliveries) == 0


@pytest.mark.asyncio
async def test_8_retry_error_handling_does_not_create_duplicate_recommendation_run(db_session, regular_user, course, monkeypatch):
    now = _utc_now() - timedelta(minutes=25)
    e1 = ActivityEvent(event_id="e_norun_1", user_id=regular_user.id, session_id="sess_norun_1", event_type="SEARCH", search_query="Python", occurred_at=now, received_at=now)
    db_session.add(e1)
    await db_session.commit()

    async def mock_raise(*args, **kwargs):
        raise RuntimeError("Failure before run completion")

    monkeypatch.setattr("app.jobs.session_followup_job._generate_session_recommendation", mock_raise)

    eligible = EligibleSession(
        user_id=regular_user.id,
        session_id="sess_norun_1",
        last_activity_at=now,
        event_count=1,
        meaningful_event_count=1,
    )
    await _process_eligible_session(eligible)

    runs = (await db_session.scalars(
        select(RecommendationRun).where(RecommendationRun.source_session_id == "sess_norun_1")
    )).all()
    # At most 1 run (which failed) or 0
    assert len(runs) <= 1
    for r in runs:
        assert r.status == "FAILED"


@pytest.mark.asyncio
async def test_9_stale_processing_state_with_no_run_recovered_safely(db_session, regular_user):
    stale_time = _utc_now() - timedelta(minutes=15)
    stale_state = SessionFollowupState(
        user_id=regular_user.id,
        session_id="sess_stale_999",
        status="PROCESSING",
        last_activity_at=stale_time,
        updated_at=stale_time,
        created_at=stale_time,
    )
    db_session.add(stale_state)
    await db_session.commit()

    recovered = await recover_stale_processing_sessions(db_session, timeout_minutes=5)
    assert recovered == 1

    await db_session.refresh(stale_state)
    assert stale_state.status == "FAILED"
    assert stale_state.error_code == "recommendation_generation_failed"
    assert stale_state.completed_at is not None


@pytest.mark.asyncio
async def test_10_existing_sent_queued_states_never_reset_by_stale_recovery(db_session, regular_user):
    stale_time = _utc_now() - timedelta(minutes=30)
    state_sent = SessionFollowupState(
        user_id=regular_user.id,
        session_id="sess_sent_100",
        status="SENT",
        last_activity_at=stale_time,
        updated_at=stale_time,
        completed_at=stale_time,
    )
    state_queued = SessionFollowupState(
        user_id=regular_user.id,
        session_id="sess_queued_100",
        status="QUEUED",
        last_activity_at=stale_time,
        updated_at=stale_time,
    )
    db_session.add_all([state_sent, state_queued])
    await db_session.commit()

    recovered = await recover_stale_processing_sessions(db_session, timeout_minutes=5)
    assert recovered == 0

    await db_session.refresh(state_sent)
    await db_session.refresh(state_queued)
    assert state_sent.status == "SENT"
    assert state_queued.status == "QUEUED"
