import pytest
from sqlalchemy import func, select

import scripts.seed_data as seed_script
from app.models import Course, VectorOutbox
from scripts.seed_data import SEED_COURSES, main as seed_main


@pytest.mark.asyncio
async def test_seed_script_idempotency(db_session):
    # First seed run
    await seed_main(reset=True)

    async with seed_script.async_session_maker() as session:
        courses_count_1 = await session.scalar(select(func.count(Course.id)))
        outbox_count_1 = await session.scalar(select(func.count(VectorOutbox.id)))

    assert courses_count_1 == 60
    assert outbox_count_1 == 60

    # Second seed run (without reset)
    await seed_main(reset=False)

    async with seed_script.async_session_maker() as session:
        courses_count_2 = await session.scalar(select(func.count(Course.id)))
        outbox_count_2 = await session.scalar(select(func.count(VectorOutbox.id)))

    # Counts should remain identical
    assert courses_count_2 == courses_count_1
    assert outbox_count_2 == outbox_count_1


def test_seed_definitions_are_explicit_and_valid():
    assert len(SEED_COURSES) == 60
    assert len({item["slug"] for item in SEED_COURSES}) == 60
    assert all(item["tags"] and all(tag == tag.strip().lower() for tag in item["tags"]) for item in SEED_COURSES)
    mapping = {item["title"]: item["category"] for item in SEED_COURSES}
    assert mapping["TypeScript for Backend Teams"] == "Web Development"
    assert mapping["Building Secure AI Products"] == "Cybersecurity"
    assert mapping["Multi-Agent Orchestration"] == "Agentic AI"


@pytest.mark.asyncio
async def test_seed_sync_preserves_course_id_and_queues_changed_course(db_session):
    await seed_main(reset=True)
    course = await db_session.scalar(select(Course).where(Course.slug == "python-for-beginners"))
    course_id = course.id
    course.category = "Artificial Intelligence"
    await db_session.commit()
    result = await seed_main(sync_existing=True)
    await db_session.refresh(course)
    assert result["changed"] == 1
    assert course.id == course_id
    assert course.category == "Python"
    assert course.version == 2
    assert await db_session.scalar(select(func.count(VectorOutbox.id)).where(VectorOutbox.course_id == course_id)) == 2
