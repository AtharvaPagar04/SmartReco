from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models import ActivityEvent, Course, User
from app.security import hash_password
from tests.conftest import csrf


@pytest.mark.asyncio
async def test_suggestions_are_sql_backed_ranked_and_active_only(client, db_session):
    db_session.add_all([
        Course(title="Python for Beginners", slug="python-for-beginners-search", short_description="Learn Python basics.", description="A practical Python foundations course with exercises.", category="Python", tags=["python", "fundamentals"], price=0, currency="USD", difficulty="BEGINNER", instructor="Asha Menon", duration_minutes=90, is_active=True, is_featured=True),
        Course(title="Python Automation Studio", slug="python-automation-studio-search", short_description="Automate useful work.", description="Build small Python automation tools.", category="Python", tags=["automation", "python"], price=10, currency="USD", difficulty="INTERMEDIATE", instructor="Ravi Shah", duration_minutes=120, is_active=True),
        Course(title="Python Archive", slug="python-archive-search", short_description="Archived Python course.", description="This course is not public.", category="Python", tags=["python"], price=10, currency="USD", difficulty="BEGINNER", instructor="Hidden", duration_minutes=60, is_active=False),
    ])
    await db_session.commit()

    response = await client.get("/api/search/suggestions?q=%20py%20&limit=100")
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "py"
    assert len(data["suggestions"]) <= 10
    assert "Python for Beginners" in [item["label"] for item in data["suggestions"]]
    assert "Python Archive" not in [item["label"] for item in data["suggestions"]]
    assert response.headers["cache-control"] == "no-store"

    category_items = [item for item in (await client.get("/api/search/suggestions?q=Python")).json()["suggestions"] if item["type"] == "category"]
    assert len(category_items) == 1
    assert (await client.get("/api/search/suggestions?q=p")).json()["suggestions"] == []
    assert (await client.get("/api/search/suggestions?q=py%25")).status_code == 200
    assert await db_session.scalar(select(func.count(ActivityEvent.id))) == 0


@pytest.mark.asyncio
async def test_recent_searches_are_private_normalized_and_bounded(client, db_session, regular_user):
    other = User(full_name="Other Student", email="other@example.com", password_hash=hash_password("OtherPass123!"))
    db_session.add(other)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    events = []
    for index, query in enumerate([" Python ", "python", "Agentic AI", "", "   "]):
        events.append(ActivityEvent(event_id=str(uuid4()), user_id=regular_user.id, session_id="user-session", event_type="SEARCH", search_query=query, occurred_at=now + timedelta(minutes=index), received_at=now))
    events.append(ActivityEvent(event_id=str(uuid4()), user_id=other.id, session_id="other-session", event_type="SEARCH", search_query="Private search", occurred_at=now + timedelta(minutes=10), received_at=now))
    db_session.add_all(events)
    await db_session.commit()

    anonymous = await client.get("/api/search/recent")
    assert anonymous.json() == {"recent_searches": []}
    assert anonymous.headers["cache-control"] == "private, no-store"

    login = await client.get("/login")
    await client.post("/login", data={"email": regular_user.email, "password": "StudentPass123!", "csrf_token": csrf(login.text)})
    response = await client.get("/api/search/recent")
    assert response.status_code == 200
    queries = [item["query"] for item in response.json()["recent_searches"]]
    assert queries[:2] == ["Agentic AI", "python"]
    assert len([query for query in queries if query.casefold() == "python"]) == 1
    assert "Private search" not in queries
