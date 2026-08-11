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
from app.services.event_service import ingest_events, server_session_id
from app.services.session_followup_service import (
    find_eligible_sessions,
    get_user_email_preference,
)
from app.jobs.session_followup_job import scan_session_followups
from app.schemas.event import EventInput


def _utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)



@pytest.mark.asyncio
async def test_continuous_activity_within_window_uses_one_session_id(db_session, regular_user):
    sess_id = "sess_continuous_1"
    now = _utc_now()

    e1 = EventInput(event_type="SEARCH", search_query="FastAPI", session_id=sess_id, occurred_at=now)
    e2 = EventInput(event_type="PAGE_VIEW", page_path="/courses", session_id=sess_id, occurred_at=now + timedelta(minutes=5))

    await ingest_events(db_session, [(0, e1), (1, e2)], user_id=regular_user.id, session_id=sess_id)

    events = (await db_session.scalars(
        select(ActivityEvent).where(ActivityEvent.user_id == regular_user.id).order_by(ActivityEvent.occurred_at)
    )).all()

    assert len(events) == 2
    assert events[0].session_id == sess_id
    assert events[1].session_id == sess_id


@pytest.mark.asyncio
async def test_activity_after_inactivity_threshold_generates_new_session_id(db_session, regular_user):
    sess_initial = "sess_initial_1"
    now = _utc_now() - timedelta(minutes=30)

    e1 = EventInput(event_type="SEARCH", search_query="Python", session_id=sess_initial, occurred_at=now)
    await ingest_events(db_session, [(0, e1)], user_id=regular_user.id, session_id=sess_initial)

    # Activity after 20 minutes (> 15 min threshold) simulates client generating new session_id
    sess_new = "sess_new_after_inactivity"
    e2 = EventInput(event_type="SEARCH", search_query="AsyncIO", session_id=sess_new, occurred_at=now + timedelta(minutes=20))
    await ingest_events(db_session, [(0, e2)], user_id=regular_user.id, session_id=sess_new)

    events = (await db_session.scalars(
        select(ActivityEvent).where(ActivityEvent.user_id == regular_user.id).order_by(ActivityEvent.occurred_at)
    )).all()

    assert len(events) == 2
    assert events[0].session_id == sess_initial
    assert events[1].session_id == sess_new
    assert events[0].session_id != events[1].session_id


@pytest.mark.asyncio
async def test_terminal_session_never_receives_newly_resumed_activity(db_session, regular_user):
    sess_term = "sess_terminal_100"
    now = _utc_now() - timedelta(minutes=40)

    # Create terminal followup state
    state = SessionFollowupState(
        user_id=regular_user.id,
        session_id=sess_term,
        status="SKIPPED_LOW_SIGNAL",
        completed_at=now,
    )
    db_session.add(state)
    await db_session.commit()

    # Attempt to ingest new activity using the old terminal session_id
    resumed_event = EventInput(event_type="SEARCH", search_query="Machine Learning", session_id=sess_term, occurred_at=_utc_now())
    session_dict = {"session_id": sess_term}

    accepted, _, _ = await ingest_events(
        db_session,
        [(0, resumed_event)],
        user_id=regular_user.id,
        session_id=sess_term,
        session_dict=session_dict,
    )

    assert accepted == 1

    # Verify event was NOT assigned to sess_term
    events_in_term = (await db_session.scalars(
        select(ActivityEvent).where(ActivityEvent.session_id == sess_term)
    )).all()
    assert len(events_in_term) == 0

    # Verify session_dict was rotated to a new session_id
    assert session_dict["session_id"] != sess_term

    # Verify the event was saved under the rotated session_id
    new_event = (await db_session.scalars(
        select(ActivityEvent).where(ActivityEvent.user_id == regular_user.id)
    )).one()
    assert new_event.session_id == session_dict["session_id"]


@pytest.mark.asyncio
async def test_new_session_after_terminal_session_can_become_eligible(db_session, regular_user):
    sess_term = "sess_terminal_200"
    t_old = _utc_now() - timedelta(hours=2)

    # Terminal session state
    state = SessionFollowupState(
        user_id=regular_user.id,
        session_id=sess_term,
        status="SENT",
        completed_at=t_old,
    )
    db_session.add(state)
    await db_session.commit()

    # New session activity past cooldown window (3 hours ago)
    sess_new = "sess_active_300"
    t_new = _utc_now() - timedelta(minutes=25)
    e1 = ActivityEvent(
        event_id="e_new_1",
        user_id=regular_user.id,
        session_id=sess_new,
        event_type="SEARCH",
        search_query="FastAPI masterclass",
        occurred_at=t_new,
        received_at=t_new,
    )
    db_session.add(e1)
    await db_session.commit()

    eligible = await find_eligible_sessions(db_session)
    session_ids = [s.session_id for s in eligible]

    assert sess_term not in session_ids
    assert sess_new in session_ids


@pytest.mark.asyncio
async def test_old_terminal_session_is_never_regenerated_or_resent(db_session, regular_user, course, monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "console")
    sess_term = "sess_terminal_400"
    t_old = _utc_now() - timedelta(hours=2)

    state = SessionFollowupState(
        user_id=regular_user.id,
        session_id=sess_term,
        status="SKIPPED_LOW_SIGNAL",
        completed_at=t_old,
    )
    db_session.add(state)
    await db_session.commit()

    # Run scan
    await scan_session_followups()

    await db_session.refresh(state)
    assert state.status == "SKIPPED_LOW_SIGNAL"
    assert state.recommendation_run_id is None
    assert state.recommendation_delivery_id is None


@pytest.mark.asyncio
async def test_no_duplicate_recommendation_run_occurs_for_old_session(db_session, regular_user, course, monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "console")
    sess_id = "sess_dedupe_500"
    now = _utc_now() - timedelta(minutes=25)

    pref = RecommendationPreference(user_id=regular_user.id, session_followup_email_enabled=True)
    db_session.add(pref)

    e1 = ActivityEvent(event_id="dedupe_1", user_id=regular_user.id, session_id=sess_id, event_type="SEARCH", search_query="Python Foundations", occurred_at=now, received_at=now)
    e2 = ActivityEvent(event_id="dedupe_2", user_id=regular_user.id, session_id=sess_id, event_type="COURSE_VIEW", course_id=course.id, occurred_at=now + timedelta(minutes=1), received_at=now + timedelta(minutes=1))
    db_session.add_all([e1, e2])
    await db_session.commit()

    # First scan processing
    await scan_session_followups()

    runs_1 = (await db_session.scalars(select(RecommendationRun).where(RecommendationRun.source_session_id == sess_id))).all()
    assert len(runs_1) == 1

    # Second scan execution
    await scan_session_followups()

    runs_2 = (await db_session.scalars(select(RecommendationRun).where(RecommendationRun.source_session_id == sess_id))).all()
    assert len(runs_2) == 1


@pytest.mark.asyncio
async def test_legacy_user_visiting_account_obtains_recommendation_preference(client, db_session):
    # Create legacy user without RecommendationPreference
    legacy_user = User(
        full_name="Legacy Learner",
        email="legacy@example.com",
        password_hash="hash_legacy_123",
        role="USER",
    )
    db_session.add(legacy_user)
    await db_session.commit()
    await db_session.refresh(legacy_user)

    # Ensure no preference row exists
    pref_before = await db_session.get(RecommendationPreference, legacy_user.id)
    assert pref_before is None

    # Perform GET /account logged in as legacy_user
    with pytest.MonkeyPatch.context() as mp:
        from app.dependencies import get_user
        from app.main import app
        app.dependency_overrides[get_user] = lambda: legacy_user

        response = await client.get("/account")
        assert response.status_code == 200

        app.dependency_overrides.clear()

    # Verify RecommendationPreference was auto-provisioned
    pref_after = await db_session.get(RecommendationPreference, legacy_user.id)
    assert pref_after is not None
    assert pref_after.recommendations_enabled is True
    assert pref_after.session_followup_email_enabled is True


@pytest.mark.asyncio
async def test_user_preference_opt_out_remains_respected(db_session, regular_user, course):
    sess_id = "sess_opt_out_600"
    now = _utc_now() - timedelta(minutes=25)

    # Set user preference opt-out
    pref = RecommendationPreference(
        user_id=regular_user.id,
        recommendations_enabled=True,
        session_followup_email_enabled=False,
    )
    db_session.add(pref)

    e1 = ActivityEvent(event_id="opt_1", user_id=regular_user.id, session_id=sess_id, event_type="SEARCH", search_query="Python", occurred_at=now, received_at=now)
    e2 = ActivityEvent(event_id="opt_2", user_id=regular_user.id, session_id=sess_id, event_type="COURSE_VIEW", course_id=course.id, occurred_at=now + timedelta(minutes=1), received_at=now + timedelta(minutes=1))
    db_session.add_all([e1, e2])
    await db_session.commit()

    # Verify get_user_email_preference returns False
    pref_status = await get_user_email_preference(db_session, regular_user.id)
    assert pref_status is False

    # Run scan
    await scan_session_followups()

    state = await db_session.scalar(
        select(SessionFollowupState).where(
            SessionFollowupState.user_id == regular_user.id,
            SessionFollowupState.session_id == sess_id,
        )
    )
    assert state is not None
    assert state.status == "SKIPPED_COOLDOWN" or state.skip_reason == "email_preference_disabled"
    assert state.recommendation_delivery_id is None

    deliveries = (await db_session.scalars(select(RecommendationDelivery).where(RecommendationDelivery.user_id == regular_user.id))).all()
    assert len(deliveries) == 0
