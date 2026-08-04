from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import ActivityEvent, RecommendationItem, RecommendationRun, RecommendationState
from app.services.interest_profile_service import build_or_refresh_profile
from app.services.recommendation_copy_service import RecommendationOutput, RecommendationOutputItem, validate_recommendation
from app.services.recommendation_email_service import render_digest
from app.services.recommendation_ranking_service import rank_candidates
from app.services.recommendation_retrieval_service import RecommendationCandidate
from app.services.recommendation_service import generate_recommendation


@pytest.mark.asyncio
async def test_profile_weights_engagement_and_reuses_unchanged_snapshot(db_session, regular_user, course):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.add_all([
        ActivityEvent(event_id=str(uuid4()), user_id=regular_user.id, session_id="s", event_type="COURSE_IMPRESSION", course_id=course.id, occurred_at=now, received_at=now),
        ActivityEvent(event_id=str(uuid4()), user_id=regular_user.id, session_id="s", event_type="COURSE_CLICK", course_id=course.id, occurred_at=now, received_at=now),
        ActivityEvent(event_id=str(uuid4()), user_id=regular_user.id, session_id="s", event_type="DWELL", course_id=course.id, duration_ms=60000, occurred_at=now, received_at=now),
    ])
    await db_session.commit()
    profile = await build_or_refresh_profile(db_session, regular_user.id)
    assert profile.profile_json["top_categories"][0]["name"] == "Python"
    assert profile.profile_json["signal_summary"]["qualified_impressions"] == 1
    same = await build_or_refresh_profile(db_session, regular_user.id)
    assert same.id == profile.id
    assert same.version == profile.version


@pytest.mark.asyncio
async def test_event_dirty_state_is_created_for_authenticated_behavior(db_session, regular_user):
    state = RecommendationState(user_id=regular_user.id, dirty_since=datetime.now(timezone.utc).replace(tzinfo=None))
    db_session.add(state)
    await db_session.commit()
    assert await db_session.get(RecommendationState, regular_user.id)


def test_ranker_is_bounded_and_deterministic(course):
    profile = {"top_categories": [{"name": "Python", "score": 1}], "top_tags": [{"name": "python", "score": 1}], "top_search_terms": [{"term": "python", "score": 1}], "recent_course_ids": [], "signal_summary": {"dwell_seconds": 120}}
    candidates = [RecommendationCandidate(course=course, semantic_score=0.9, evidence={"source": "test"})]
    first = rank_candidates(candidates, profile, limit=1)[0]
    second = rank_candidates([RecommendationCandidate(course=course, semantic_score=0.9, evidence={"source": "test"})], profile, limit=1)[0]
    assert 0 <= first.deterministic_score <= 1
    assert first.deterministic_score == second.deterministic_score


def test_grounding_rejects_unknown_course(course):
    output = RecommendationOutput(headline="A useful next step", narrative="This is a grounded explanation based on your recent course activity and the supplied catalog evidence.", recommendations=[RecommendationOutputItem(course_id="not-a-course", reason="This reason is long enough to pass the field validation.")])
    with pytest.raises(ValueError):
        validate_recommendation(output, [], 3)


@pytest.mark.asyncio
async def test_no_llm_generation_persists_deterministic_fallback(db_session, regular_user, course, monkeypatch):
    monkeypatch.setattr(settings, "mesh_api_key", "")
    monkeypatch.setattr(settings, "mesh_chat_model", "")
    status, run_id, _ = await generate_recommendation(db_session, regular_user.id, trigger_type="ADMIN_TEST", force=True)
    assert status == "COMPLETED"
    run = await db_session.get(RecommendationRun, run_id)
    assert run.status == "FALLBACK_SUCCEEDED"
    assert run.used_llm_fallback is True
    items = list((await db_session.scalars(select(RecommendationItem).where(RecommendationItem.run_id == run.id))).all())
    assert all(item.evidence_json for item in items)


def test_email_html_escapes_catalog_copy():
    class Course:
        slug = "safe"
        title = "<Unsafe course>"
        is_active = True

    class Item:
        dismissed_at = None
        course = Course()
        reason = "<reason>"

    class Run:
        headline = "<headline>"
        narrative = "<narrative>"
        items = [Item()]

    text, html = render_digest(Run())
    assert "&lt;headline&gt;" in html
    assert "<Unsafe course>" not in html
    assert "<reason>" in text
