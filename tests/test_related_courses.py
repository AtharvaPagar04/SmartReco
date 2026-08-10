import asyncio
from types import SimpleNamespace

import pytest

from app.config import settings
from app.models import Course, UserInterestProfile
from app.services.related_course_service import get_related_courses
from app.services.vector_store import VectorCourseHit


def make_course(**overrides):
    values = {
        "title": "Related Python Course",
        "slug": "related-python-course",
        "short_description": "A related course for practical Python work.",
        "description": "Build useful Python skills with focused exercises.",
        "category": "Python",
        "tags": ["python", "practice"],
        "price": 25,
        "currency": "USD",
        "difficulty": "BEGINNER",
        "instructor": "Ravi Shah",
        "duration_minutes": 90,
        "is_featured": False,
        "is_active": True,
        "version": 1,
        "vector_status": "SYNCED",
    }
    values.update(overrides)
    return Course(**values)


def valid_test_vector():
    return [0.1 + i * 0.0001 for i in range(settings.vector_size)]


class FakeStore:
    def __init__(self, hits=None, error=None, query_vector=None):
        self.hits = hits or []
        self.error = error
        self.query_vector = query_vector or valid_test_vector()

    async def get_point(self, course_id, *, with_vectors=False):
        if self.error:
            raise self.error
        return SimpleNamespace(
            payload={
                "course_id": course_id,
                "is_active": True,
                "version": 1,
                "embedding_model": settings.mesh_embedding_model,
                "embedding_dimension": settings.vector_size,
                "embedding_schema_version": settings.embedding_schema_version,
            },
            vector=self.query_vector,
        )

    async def search_courses(self, query_vector, *, limit, filters=None):
        return self.hits


@pytest.mark.asyncio
async def test_related_courses_returns_two_active_courses_and_excludes_current(db_session, course):
    related_one = make_course(slug="python-automation", title="Python Automation", tags=["python", "automation"])
    related_two = make_course(slug="fastapi-foundations", title="FastAPI Foundations", tags=["python", "web"])
    archived = make_course(slug="archived-python", title="Archived Python", is_active=False)
    db_session.add_all([related_one, related_two, archived])
    await db_session.commit()

    result = await get_related_courses(db_session, course, store=FakeStore(error=RuntimeError("qdrant unavailable")))
    assert len(result) == 2
    assert course.id not in {item.course.id for item in result}
    assert archived.id not in {item.course.id for item in result}


@pytest.mark.asyncio
async def test_semantic_candidates_are_sql_reloaded_and_deterministically_ranked(db_session, course):
    related_one = make_course(slug="agentic-python", title="Agentic Python", category="Python", tags=["python", "agents"])
    related_two = make_course(slug="python-data", title="Python Data Lab", category="Data Science", tags=["python", "data"])
    db_session.add_all([related_one, related_two])
    await db_session.commit()

    hits = [
        VectorCourseHit(related_two.id, 0.75, {"course_id": related_two.id, "is_active": True, "version": 1, "embedding_model": settings.mesh_embedding_model, "embedding_dimension": settings.vector_size, "embedding_schema_version": settings.embedding_schema_version}),
        VectorCourseHit(related_one.id, 0.65, {"course_id": related_one.id, "is_active": True, "version": 1, "embedding_model": settings.mesh_embedding_model, "embedding_dimension": settings.vector_size, "embedding_schema_version": settings.embedding_schema_version}),
        VectorCourseHit(course.id, 1.0, {"course_id": course.id, "is_active": True}),
    ]
    result = await get_related_courses(db_session, course, store=FakeStore(hits=hits))
    assert [item.course.title for item in result] == ["Agentic Python", "Python Data Lab"]
    assert all(item.source == "semantic" for item in result)
    assert all(item.score <= 1 for item in result)


@pytest.mark.asyncio
async def test_user_activity_personalizes_related_course_ranking(db_session, regular_user, course):
    c1 = make_course(slug="python-advanced", title="Advanced Python Patterns", category="Python", tags=["python", "oop"])
    c2 = make_course(slug="python-web", title="Python Web APIs", category="Python", tags=["python", "api", "web"])
    db_session.add_all([c1, c2])
    await db_session.commit()

    profile_data = {
        "confidence": 0.9,
        "top_categories": [{"name": "Python", "score": 0.8}],
        "top_tags": [{"name": "api", "score": 0.9}, {"name": "web", "score": 0.8}],
    }
    profile_record = UserInterestProfile(
        user_id=regular_user.id,
        profile_hash="test_hash_1",
        profile_json=profile_data,
        window_started_at=course.created_at,
        window_ended_at=course.created_at,
        generated_at=course.created_at,
    )
    db_session.add(profile_record)
    await db_session.commit()

    result = await get_related_courses(
        db_session,
        course,
        user_id=regular_user.id,
        store=FakeStore(error=RuntimeError("qdrant down")),
    )
    assert len(result) == 2
    assert result[0].course.title == "Python Web APIs"
    assert "matches your recent api learning activity" in result[0].reason


@pytest.mark.asyncio
async def test_hard_relevance_gate_prevents_unrelated_personalization_override(db_session, regular_user):
    current_course = make_course(slug="react-fundamentals", title="React Fundamentals", category="Frontend", tags=["react", "javascript"])
    relevant_course = make_course(slug="vue-foundations", title="Vue Foundations", category="Frontend", tags=["vue", "javascript"])
    unrelated_course = make_course(slug="kubernetes-ops", title="Kubernetes Cluster Ops", category="DevOps", tags=["kubernetes", "docker"])
    db_session.add_all([current_course, relevant_course, unrelated_course])
    await db_session.commit()

    profile_data = {
        "confidence": 1.0,
        "top_categories": [{"name": "DevOps", "score": 1.0}],
        "top_tags": [{"name": "kubernetes", "score": 1.0}],
    }
    profile_record = UserInterestProfile(
        user_id=regular_user.id,
        profile_hash="test_hash_2",
        profile_json=profile_data,
        window_started_at=current_course.created_at,
        window_ended_at=current_course.created_at,
        generated_at=current_course.created_at,
    )
    db_session.add(profile_record)
    await db_session.commit()

    result = await get_related_courses(
        db_session,
        current_course,
        user_id=regular_user.id,
        store=FakeStore(error=RuntimeError("qdrant down")),
    )
    assert len(result) >= 1
    result_ids = {item.course.id for item in result}
    assert relevant_course.id in result_ids
    assert unrelated_course.id not in result_ids


@pytest.mark.asyncio
async def test_invalid_constant_vector_triggers_safe_fallback(db_session, course):
    c1 = make_course(slug="c1-python", title="Course 1 Python")
    c2 = make_course(slug="c2-python", title="Course 2 Python")
    db_session.add_all([c1, c2])
    await db_session.commit()

    store = FakeStore(query_vector=[0.1] * settings.vector_size)
    result = await get_related_courses(db_session, course, store=store)
    assert len(result) == 2
    assert all(item.source == "sql" for item in result)


@pytest.mark.asyncio
async def test_timeout_uses_sql_fallback_without_mesh_or_profile(db_session, course, monkeypatch):
    related_one = make_course(slug="python-one")
    related_two = make_course(slug="python-two")
    db_session.add_all([related_one, related_two])
    await db_session.commit()
    monkeypatch.setattr(settings, "related_courses_timeout_seconds", 0.01)

    class SlowStore(FakeStore):
        async def get_point(self, course_id, *, with_vectors=False):
            await asyncio.sleep(1)

    result = await get_related_courses(db_session, course, store=SlowStore())
    assert len(result) == 2
    assert all(item.source == "sql" for item in result)


@pytest.mark.asyncio
async def test_course_detail_renders_contextual_cards_and_router_failure_is_graceful(client, db_session, course, monkeypatch):
    related_one = make_course(slug="detail-related-one", title="Detail Related One")
    related_two = make_course(slug="detail-related-two", title="Detail Related Two")
    db_session.add_all([related_one, related_two])
    await db_session.commit()

    response = await client.get(f"/courses/{course.slug}")
    assert response.status_code == 200
    assert response.text.count('data-related-course data-course-id=') == 2
    assert "Related courses" in response.text
    assert response.text.count('data-related-course-click') == 2

    async def broken(*args, **kwargs):
        raise RuntimeError("dependency unavailable")

    monkeypatch.setattr("app.routers.catalog.get_related_courses", broken)
    degraded = await client.get(f"/courses/{course.slug}")
    assert degraded.status_code == 200
    assert "Related courses" not in degraded.text


@pytest.mark.asyncio
async def test_related_section_shows_available_option_when_catalog_is_small(client, db_session, course):
    only = make_course(slug="only-related")
    db_session.add(only)
    await db_session.commit()
    response = await client.get(f"/courses/{course.slug}")
    assert response.status_code == 200
    assert "Related courses" in response.text
    assert response.text.count('data-related-course data-course-id=') == 1


def test_related_tracking_is_distinct_from_personalized_recommendations():
    tracker = open("app/static/js/tracker.js", encoding="utf-8").read()
    assert "source: 'related_course'" in tracker
    assert "data-related-course" in tracker
    assert "recommendation_item_id" not in tracker.split("data-related-course-click", 1)[1].split("if ('IntersectionObserver'", 1)[0]
