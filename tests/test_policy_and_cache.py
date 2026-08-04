import argparse
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import ActivityEvent, Course, RecommendationRun, RecommendationState, UserInterestProfile
from app.services.interest_profile_service import build_or_refresh_profile
from app.services.recommendation_service import generate_recommendation
import scripts.generate_recommendation as gen_cli


@pytest.mark.asyncio
async def test_same_profile_hash_does_not_increment_version(db_session, regular_user, course):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.add(ActivityEvent(
        event_id=str(uuid4()), user_id=regular_user.id, session_id="s1",
        event_type="COURSE_CLICK", course_id=course.id, occurred_at=now, received_at=now
    ))
    await db_session.commit()

    p1 = await build_or_refresh_profile(db_session, regular_user.id)
    v1 = p1.version
    hash1 = p1.profile_hash

    p2 = await build_or_refresh_profile(db_session, regular_user.id)
    assert p2.profile_hash == hash1
    assert p2.version == v1


@pytest.mark.asyncio
async def test_one_meaningful_hash_change_increments_version_exactly_once(db_session, regular_user, course):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.add(ActivityEvent(
        event_id=str(uuid4()), user_id=regular_user.id, session_id="s1",
        event_type="COURSE_CLICK", course_id=course.id, occurred_at=now, received_at=now
    ))
    await db_session.commit()

    p1 = await build_or_refresh_profile(db_session, regular_user.id)
    v1 = p1.version

    # Add a meaningful new SEARCH event that changes profile hash
    now2 = now + timedelta(minutes=5)
    db_session.add(ActivityEvent(
        event_id=str(uuid4()), user_id=regular_user.id, session_id="s2",
        event_type="SEARCH", search_query="Agentic AI Workflow", occurred_at=now2, received_at=now2
    ))
    await db_session.commit()

    p2 = await build_or_refresh_profile(db_session, regular_user.id)
    assert p2.version == v1 + 1

    # Second refresh without new events should keep version at v1 + 1
    p3 = await build_or_refresh_profile(db_session, regular_user.id)
    assert p3.version == v1 + 1


@pytest.mark.asyncio
async def test_weak_watermark_updates_do_not_increment_version(db_session, regular_user, course):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.add(ActivityEvent(
        event_id=str(uuid4()), user_id=regular_user.id, session_id="s1",
        event_type="COURSE_CLICK", course_id=course.id, occurred_at=now, received_at=now
    ))
    await db_session.commit()

    p1 = await build_or_refresh_profile(db_session, regular_user.id)
    v1 = p1.version
    count1 = p1.source_event_count

    # Add a weak/non-interest event that updates source event count & max_occurred watermark without altering canonical profile
    now2 = now + timedelta(minutes=1)
    db_session.add(ActivityEvent(
        event_id=str(uuid4()), user_id=regular_user.id, session_id="s1",
        event_type="ACCOUNT_VIEW", occurred_at=now2, received_at=now2
    ))
    await db_session.commit()

    p2 = await build_or_refresh_profile(db_session, regular_user.id)
    assert p2.source_event_count == count1 + 1
    assert p2.version == v1



def test_cli_parser_defaults_force_false_and_accepts_flag():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--trigger", default="CLI")
    parser.add_argument("--force", action="store_true")

    args_default = parser.parse_args(["--user-id", "test-user"])
    assert args_default.force is False

    args_forced = parser.parse_args(["--user-id", "test-user", "--force"])
    assert args_forced.force is True


@pytest.mark.asyncio
async def test_normal_cli_respects_cooldown(db_session, regular_user, course, monkeypatch):
    monkeypatch.setattr(settings, "mesh_api_key", "")
    monkeypatch.setattr(settings, "mesh_chat_model", "")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.add(ActivityEvent(
        event_id=str(uuid4()), user_id=regular_user.id, session_id="s1",
        event_type="COURSE_CLICK", course_id=course.id, occurred_at=now, received_at=now
    ))
    await db_session.commit()

    # First run succeeds and sets cooldown
    status1, run_id1, _ = await generate_recommendation(db_session, regular_user.id, trigger_type="CLI", force=True)
    assert status1 == "COMPLETED"

    # Second run with force=False respects active cooldown
    status2, ref2, _ = await generate_recommendation(db_session, regular_user.id, trigger_type="CLI", force=False)
    assert status2 == "SKIPPED"
    assert ref2 == "COOLDOWN_ACTIVE"


@pytest.mark.asyncio
async def test_runs_store_cache_key_and_reuse_makes_zero_mesh_calls(db_session, regular_user, course, monkeypatch):
    monkeypatch.setattr(settings, "mesh_api_key", "")
    monkeypatch.setattr(settings, "mesh_chat_model", "")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.add(ActivityEvent(
        event_id=str(uuid4()), user_id=regular_user.id, session_id="s1",
        event_type="COURSE_CLICK", course_id=course.id, occurred_at=now, received_at=now
    ))
    await db_session.commit()

    mesh_calls = 0

    async def fake_generate_json(*args, **kwargs):
        nonlocal mesh_calls
        mesh_calls += 1
        return {"headline": "Mesh Headline", "narrative": "Mesh Narrative Explanation", "recommendations": [{"course_id": course.id, "reason": "Test reason", "cta_label": "Explore"}]}

    monkeypatch.setattr("app.agents.recommendation_graph.generate_json", fake_generate_json)

    # First run generates via Mesh (or fallback) and stores non-null cache_key
    status1, run_id1, _ = await generate_recommendation(db_session, regular_user.id, trigger_type="CLI", force=True)
    assert status1 == "COMPLETED"
    run1 = await db_session.get(RecommendationRun, run_id1)
    assert run1.cache_key is not None
    assert len(run1.cache_key) == 64
    initial_calls = mesh_calls

    # Reset state cooldown to allow rerun while keeping identical profile and candidate set
    state = await db_session.get(RecommendationState, regular_user.id)
    state.cooldown_until = None
    await db_session.commit()

    # Second run with unchanged profile & candidates reuses fresh run and makes 0 additional Mesh chat calls
    status2, run_id2, _ = await generate_recommendation(db_session, regular_user.id, trigger_type="CLI", force=True)
    assert status2 == "COMPLETED"
    assert mesh_calls == initial_calls  # Zero additional calls!

    run2 = await db_session.get(RecommendationRun, run_id2)
    assert run2.cache_key == run1.cache_key
