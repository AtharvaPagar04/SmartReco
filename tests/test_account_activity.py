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
    assert "Ongoing & Completed Courses" in response.text
    assert "Skills Acquired" in response.text
    assert "COURSE_IMPRESSION" not in response.text



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


@pytest.mark.asyncio
async def test_update_user_profile_details(client, db_session, regular_user):
    login = await client.get("/login")
    await client.post("/login", data={"email": regular_user.email, "password": "StudentPass123!", "csrf_token": csrf(login.text)})

    account_page = await client.get("/account")
    assert account_page.status_code == 200

    response = await client.post(
        "/account/profile",
        data={
            "csrf_token": csrf(account_page.text),
            "full_name": "Updated Ada Lovelace",
            "headline": "Lead AI Architect",
            "bio": "Building autonomous systems and smart recommendation pipelines.",
            "location": "London, UK",
            "primary_domain": "Machine Learning & AI",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Updated Ada Lovelace" in response.text
    assert "Lead AI Architect" in response.text
    assert "London, UK" in response.text

    await db_session.refresh(regular_user)
    assert regular_user.full_name == "Updated Ada Lovelace"
    assert regular_user.headline == "Lead AI Architect"
    assert regular_user.location == "London, UK"
    assert regular_user.primary_domain == "Machine Learning & AI"


@pytest.mark.asyncio
async def test_complete_course_updates_enrollment_and_skills(client, db_session, regular_user, course):
    login = await client.get("/login")
    await client.post("/login", data={"email": regular_user.email, "password": "StudentPass123!", "csrf_token": csrf(login.text)})

    # First enroll in the course
    detail_page = await client.get(f"/courses/{course.slug}")
    assert detail_page.status_code == 200

    enroll_res = await client.post(f"/courses/{course.slug}/enroll", data={"csrf_token": csrf(detail_page.text)}, follow_redirects=True)
    assert enroll_res.status_code == 200

    # Now mark as complete
    complete_res = await client.post(f"/courses/{course.slug}/complete", data={"csrf_token": csrf(enroll_res.text)}, follow_redirects=True)
    assert complete_res.status_code == 200
    assert "Completed" in complete_res.text or "Review course" in complete_res.text

    # Check account page shows completed course and acquired skills
    account_res = await client.get("/account")
    assert account_res.status_code == 200
    assert "Completed Courses" in account_res.text
    assert course.title in account_res.text

