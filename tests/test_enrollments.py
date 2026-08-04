import pytest
from sqlalchemy import select

from app.models import Course, Enrollment
from app.services.recommendation_retrieval_service import retrieve_sql_fallback
from app.services.related_course_service import get_related_courses
from tests.conftest import csrf


async def login(client, email: str, password: str) -> None:
    page = await client.get("/login")
    response = await client.post("/login", data={"email": email, "password": password, "csrf_token": csrf(page.text)})
    assert response.status_code == 303


@pytest.mark.asyncio
async def test_anonymous_start_action_and_authenticated_enrollment_are_csrf_protected(client, course, regular_user, db_session):
    detail = await client.get(f"/courses/{course.slug}")
    assert "Sign in to start" in detail.text
    assert "Start course" not in detail.text

    await login(client, regular_user.email, "StudentPass123!")
    denied = await client.post(f"/courses/{course.slug}/enroll")
    assert denied.status_code == 403

    token = csrf((await client.get(f"/courses/{course.slug}")).text)
    started = await client.post(f"/courses/{course.slug}/enroll", data={"csrf_token": token})
    assert started.status_code == 303
    assert started.headers["location"] == f"/courses/{course.slug}"

    repeat = await client.post(f"/courses/{course.slug}/enroll", data={"csrf_token": csrf((await client.get(f"/courses/{course.slug}")).text)})
    assert repeat.status_code == 303
    rows = list((await db_session.scalars(select(Enrollment).where(Enrollment.user_id == regular_user.id, Enrollment.course_id == course.id))).all())
    assert len(rows) == 1
    assert "Continue course" in (await client.get(f"/courses/{course.slug}")).text


@pytest.mark.asyncio
async def test_home_learning_is_above_featured_and_enrollment_hides_featured(client, db_session, regular_user, course):
    featured = Course(title="Featured Data", slug="featured-data", short_description="Data skills.", description="Learn data skills.", category="Data", tags=["data"], price=0, currency="USD", difficulty="BEGINNER", instructor="Asha Menon", duration_minutes=60, is_featured=True, is_active=True)
    db_session.add(featured)
    await db_session.commit()
    await login(client, regular_user.email, "StudentPass123!")
    token = csrf((await client.get(f"/courses/{course.slug}")).text)
    await client.post(f"/courses/{course.slug}/enroll", data={"csrf_token": token})

    home = await client.get("/")
    assert home.text.index("Continue learning") < home.text.index("Featured courses")
    assert course.title in home.text
    assert featured.title in home.text
    featured_start = home.text.index("Featured courses")
    assert course.title not in home.text[featured_start:]


@pytest.mark.asyncio
async def test_enrolled_courses_are_excluded_from_sql_recommendations(db_session, regular_user, course):
    other = Course(title="Other Python", slug="other-python", short_description="Other.", description="Other.", category="Python", tags=["python"], price=0, currency="USD", difficulty="BEGINNER", instructor="Asha Menon", duration_minutes=60, is_featured=True, is_active=True)
    db_session.add(other)
    await db_session.commit()
    profile = {"excluded_course_ids": [course.id], "top_categories": [], "top_tags": [], "top_search_terms": []}
    candidates = await retrieve_sql_fallback(db_session, profile, limit=10)
    assert course.id not in {item.course.id for item in candidates}
    assert other.id in {item.course.id for item in candidates}


@pytest.mark.asyncio
async def test_enrolled_courses_are_excluded_from_related_courses(db_session, regular_user, course):
    enrolled = Course(title="Enrolled Related", slug="enrolled-related", short_description="Enrolled.", description="Enrolled.", category=course.category, tags=course.tags, price=0, currency="USD", difficulty="BEGINNER", instructor="Asha Menon", duration_minutes=60, is_active=True)
    available = Course(title="Available Related", slug="available-related", short_description="Available.", description="Available.", category=course.category, tags=course.tags, price=0, currency="USD", difficulty="BEGINNER", instructor="Asha Menon", duration_minutes=60, is_active=True)
    db_session.add_all([enrolled, available])
    await db_session.commit()
    db_session.add(Enrollment(user_id=regular_user.id, course_id=enrolled.id, started_at=course.created_at, last_accessed_at=course.created_at))
    await db_session.commit()

    related = await get_related_courses(db_session, course, excluded_course_ids={enrolled.id})
    assert enrolled.id not in {item.course.id for item in related}
    assert available.id in {item.course.id for item in related}
