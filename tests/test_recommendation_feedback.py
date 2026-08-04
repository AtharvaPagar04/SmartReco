from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import RecommendationFeedback, RecommendationItem, RecommendationRun, RecommendationState
from app.repositories.recommendation_feedback import feedback_preferences_for_user, record_feedback
from tests.conftest import csrf


@pytest.mark.asyncio
async def test_feedback_is_user_scoped_idempotent_and_updates_profile_preferences(db_session, regular_user, course):
    run = RecommendationRun(user_id=regular_user.id, profile_hash="h", trigger_type="TEST", status="SUCCEEDED", headline="Path", narrative="A grounded learning path for this learner.")
    db_session.add(run)
    await db_session.flush()
    item = RecommendationItem(user_id=regular_user.id, run_id=run.id, course_id=course.id, rank=1, reason="A useful next step for Python practice.", cta_label="Explore")
    db_session.add(item)
    await db_session.commit()

    await record_feedback(db_session, user_id=regular_user.id, recommendation_item_id=item.id, reason_code="TOO_ADVANCED")
    await db_session.commit()
    await record_feedback(db_session, user_id=regular_user.id, recommendation_item_id=item.id, reason_code="PREFER_MORE_PRACTICAL")
    await db_session.commit()

    rows = list((await db_session.scalars(select(RecommendationFeedback).where(RecommendationFeedback.user_id == regular_user.id))).all())
    summary = await feedback_preferences_for_user(db_session, user_id=regular_user.id)
    assert len(rows) == 1
    assert rows[0].reason_code == "PREFER_MORE_PRACTICAL"
    assert item.dismissed_at is not None
    assert course.id in summary.excluded_course_ids
    assert summary.prefers_practical is True


@pytest.mark.asyncio
async def test_feedback_endpoint_requires_reason_and_hides_item(client, regular_user, db_session, course):
    from tests.test_recommendation_frontend import login_client

    await login_client(client, regular_user)
    run = RecommendationRun(user_id=regular_user.id, profile_hash="h", trigger_type="TEST", status="SUCCEEDED", headline="Feedback path", narrative="A grounded learning path for this learner.")
    db_session.add(run)
    await db_session.flush()
    item = RecommendationItem(user_id=regular_user.id, run_id=run.id, course_id=course.id, rank=1, reason="A useful next step for Python practice.", cta_label="Explore")
    db_session.add(item)
    await db_session.commit()
    token = csrf((await client.get("/recommendations")).text)

    response = await client.post(
        f"/api/recommendations/items/{item.id}/feedback",
        data={"csrf_token": token, "reason_code": "TOO_BASIC"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 202
    assert response.json()["dismissed_item_id"] == item.id
    assert (await db_session.get(RecommendationState, regular_user.id)).dirty_since is None or response.json()["replacement_pending"] is True
    assert (await db_session.get(RecommendationItem, item.id)).dismissed_at is not None
