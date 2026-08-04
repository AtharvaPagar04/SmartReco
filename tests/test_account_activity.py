from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import ActivityEvent
from tests.conftest import csrf


@pytest.mark.asyncio
async def test_account_activity_is_summarized(client, db_session, regular_user, course):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.add_all([
        ActivityEvent(event_id=str(uuid4()), user_id=regular_user.id, session_id="session-one", event_type="COURSE_IMPRESSION", course_id=course.id, page_path="/courses", occurred_at=now, received_at=now),
        ActivityEvent(event_id=str(uuid4()), user_id=regular_user.id, session_id="session-one", event_type="COURSE_VIEW", course_id=course.id, page_path=f"/courses/{course.slug}", occurred_at=now, received_at=now),
        ActivityEvent(event_id=str(uuid4()), user_id=regular_user.id, session_id="session-one", event_type="DWELL", course_id=course.id, duration_ms=600000, page_path=f"/courses/{course.slug}", occurred_at=now, received_at=now),
        ActivityEvent(event_id=str(uuid4()), user_id=regular_user.id, session_id="session-one", event_type="SEARCH", search_query=" Python ", page_path="/courses", occurred_at=now, received_at=now),
        ActivityEvent(event_id=str(uuid4()), user_id=regular_user.id, session_id="session-one", event_type="SEARCH", search_query="python", page_path="/courses", occurred_at=now, received_at=now),
    ])
    await db_session.commit()
    client.cookies.clear()
    login = await client.get("/login")
    await client.post("/login", data={"email": regular_user.email, "password": "StudentPass123!", "csrf_token": csrf(login.text)})
    response = await client.get("/account")
    assert response.status_code == 200
    assert "Recent searches" in response.text
    assert "Categories you explored" in response.text
    assert "COURSE_IMPRESSION" not in response.text
    assert "python" in response.text.lower()


@pytest.mark.asyncio
async def test_api_events_recent_endpoint(client, db_session, regular_user, course):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.add(
        ActivityEvent(event_id=str(uuid4()), user_id=regular_user.id, session_id="session-live", event_type="COURSE_VIEW", course_id=course.id, page_path=f"/courses/{course.slug}", occurred_at=now, received_at=now)
    )
    await db_session.commit()

    # Authenticated request to /api/events/recent
    login = await client.get("/login")
    await client.post("/login", data={"email": regular_user.email, "password": "StudentPass123!", "csrf_token": csrf(login.text)})

    res = await client.get("/api/events/recent")
    assert res.status_code == 200
    data = res.json()
    assert data["authenticated"] is True
    assert len(data["recently_viewed"]) >= 1
    assert data["recently_viewed"][0]["title"] == course.title
    assert data["recently_viewed"][0]["slug"] == course.slug

