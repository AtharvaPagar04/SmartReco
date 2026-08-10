from decimal import Decimal
from unittest.mock import patch
import pytest
import pytest_asyncio

from app.models import Course, LearningPath, LearningPathItem
from app.services.learning_path_service import get_owned_path, replace_item
from tests.conftest import csrf


def make_course(
    title: str,
    category: str,
    difficulty: str = "INTERMEDIATE",
    tags: list[str] | None = None,
    price: str = "49.99",
) -> Course:
    tags = tags or []
    return Course(
        title=title,
        slug=title.lower().replace(" ", "-").replace("&", "and").replace(":", "").replace(" ", "-"),
        short_description=title,
        description=title,
        category=category,
        difficulty=difficulty,
        price=Decimal(price),
        currency="USD",
        duration_minutes=180,
        instructor="Instructor",
        tags=tags,
        what_you_will_learn=tags,
        prerequisites=[],
        target_audience=[],
        tools_used=[],
        curriculum=[],
        is_active=True,
    )


def make_path(user_id: str, primary_domain: str = "AGENTIC_AI", course_count: int = 3, total_price: Decimal = Decimal("0.00")) -> LearningPath:
    return LearningPath(
        user_id=user_id,
        title=f"{primary_domain} Path",
        summary=f"{primary_domain} Summary",
        status="READY",
        primary_domain=primary_domain,
        secondary_domains_json=[],
        goal_code="PRODUCTION",
        level_code="INTERMEDIATE",
        learning_preferences_json=[],
        weekly_hours=10,
        budget_type="FLEXIBLE",
        budget_scope="PATH",
        path_length_preference="AUTO",
        input_json={"primary_domain": primary_domain, "goals": ["PRODUCTION"], "level": "INTERMEDIATE", "weekly_hours": 10, "requested_course_count": max(3, course_count)},
        total_price=total_price,
        estimated_total_hours=9,
        estimated_weeks=1,
    )


@pytest_asyncio.fixture
async def sample_courses(db_session):
    courses = [
        make_course("Introduction to Agentic AI", "Agentic AI", "BEGINNER", ["agents", "foundations", "ai workflows"], "49.99"),
        make_course("Tool Execution & API Synthesizers", "Agentic AI", "INTERMEDIATE", ["tool calling", "api synthesis", "json schema"], "69.99"),
        make_course("Memory Architectures for Long-Context Agents", "Agentic AI", "INTERMEDIATE", ["agent memory", "vector stores", "episodes"], "79.99"),
        make_course("Autonomous Agent Evaluation & Red Teaming", "Agentic AI", "ADVANCED", ["agent evaluation", "red teaming", "safety"], "119.99"),
        make_course("Fine-Tuning Open Source LLMs for Agents", "Artificial Intelligence", "INTERMEDIATE", ["llms", "fine-tuning", "agents", "lora"], "59.99"),
        make_course("RAG Systems for Agent Knowledge", "Artificial Intelligence", "INTERMEDIATE", ["rag", "vector databases", "embeddings", "agents"], "89.99"),
    ]
    for c in courses:
        db_session.add(c)
    await db_session.commit()
    return courses


@pytest.mark.asyncio
async def test_replace_item_exact_success_and_transitions(db_session, regular_user, sample_courses):
    c1, c2, c3 = sample_courses[0], sample_courses[1], sample_courses[2]
    path = make_path(user_id=regular_user.id, primary_domain="AGENTIC_AI", course_count=3, total_price=c1.price + c2.price + c3.price)
    db_session.add(path)
    await db_session.flush()

    item1 = LearningPathItem(
        learning_path_id=path.id, course_id=c1.id, position=1, stage_label="Build the foundation",
        reason="Base", how_it_prepares_next=f"This stage prepares you for {c2.title}.",
        skills_gained_json=c1.tags, estimated_hours=3, price_snapshot=c1.price, currency="USD",
    )
    item2 = LearningPathItem(
        learning_path_id=path.id, course_id=c2.id, position=2, stage_label="Strengthen the core skill",
        reason="Core", how_it_prepares_next=f"This stage prepares you for {c3.title}.",
        skills_gained_json=c2.tags, estimated_hours=3, price_snapshot=c2.price, currency="USD",
    )
    item3 = LearningPathItem(
        learning_path_id=path.id, course_id=c3.id, position=3, stage_label="Apply the skill",
        reason="Advanced", how_it_prepares_next="This stage advances the Agentic AI outcome.",
        skills_gained_json=c3.tags, estimated_hours=3, price_snapshot=c3.price, currency="USD",
    )
    db_session.add_all([item1, item2, item3])
    await db_session.commit()

    loaded_path = await get_owned_path(db_session, regular_user.id, path.id)
    target_item = next(item for item in loaded_path.items if item.position == 2)
    prev_item = next(item for item in loaded_path.items if item.position == 1)
    next_item = next(item for item in loaded_path.items if item.position == 3)

    result = await replace_item(db_session, loaded_path, target_item, reason="ALREADY_KNOW", trace_id="test_replace_trace")
    assert result.replaced is True
    assert result.source == "EXACT_DOMAIN"
    assert "was replaced with" in result.user_message

    assert target_item.course_id not in (c1.id, c2.id, c3.id)
    assert target_item.position == 2
    assert len(loaded_path.items) == 3

    new_course = target_item.course
    assert prev_item.how_it_prepares_next == f"This stage prepares you for {new_course.title}."
    assert target_item.how_it_prepares_next == f"This stage prepares you for {next_item.course.title}."

    expected_total_price = sum(Decimal(str(item.price_snapshot)) for item in loaded_path.items)
    assert loaded_path.total_price == expected_total_price


@pytest.mark.asyncio
async def test_replace_item_related_domain_fallback(db_session, regular_user):
    rag1 = make_course("Production RAG Systems", "Artificial Intelligence", "ADVANCED", ["rag", "retrieval", "vector"], "99.99")
    rag2 = make_course("Multimodal AI System Engineering", "Artificial Intelligence", "ADVANCED", ["rag", "multimodal", "embeddings"], "109.99")
    rag3 = make_course("Vector Databases in Practice", "Artificial Intelligence", "INTERMEDIATE", ["rag", "vector", "search"], "79.99")
    rel1 = make_course("Prompt Engineering Fundamentals", "Artificial Intelligence", "BEGINNER", ["llms", "prompts", "generative ai"], "49.99")
    rel2 = make_course("Small Language Models in Edge Production", "Artificial Intelligence", "INTERMEDIATE", ["llms", "slms", "edge"], "89.99")

    db_session.add_all([rag1, rag2, rag3, rel1, rel2])
    await db_session.commit()

    path = make_path(user_id=regular_user.id, primary_domain="RAG", course_count=3, total_price=rag1.price + rag2.price + rag3.price)
    db_session.add(path)
    await db_session.flush()

    item1 = LearningPathItem(learning_path_id=path.id, course_id=rag1.id, position=1, stage_label="Foundation", reason="Base", how_it_prepares_next="Next", estimated_hours=3, price_snapshot=rag1.price, currency="USD")
    item2 = LearningPathItem(learning_path_id=path.id, course_id=rag2.id, position=2, stage_label="Core", reason="Core", how_it_prepares_next="Next", estimated_hours=3, price_snapshot=rag2.price, currency="USD")
    item3 = LearningPathItem(learning_path_id=path.id, course_id=rag3.id, position=3, stage_label="Apply", reason="Apply", how_it_prepares_next="Outcome", estimated_hours=3, price_snapshot=rag3.price, currency="USD")
    db_session.add_all([item1, item2, item3])
    await db_session.commit()

    loaded_path = await get_owned_path(db_session, regular_user.id, path.id)
    target_item = next(item for item in loaded_path.items if item.position == 3)

    result = await replace_item(db_session, loaded_path, target_item, reason="ALREADY_KNOW", trace_id="test_rag_fallback")
    assert result.replaced is True
    assert result.source == "RELATED_DOMAIN"
    assert result.reason_code == "REPLACED_RELATED"
    assert "closely related alternative" in result.user_message
    assert target_item.course_id in (rel1.id, rel2.id)


@pytest.mark.asyncio
async def test_replace_item_too_advanced_no_easier_candidate(db_session, regular_user):
    c1 = make_course("Beg Course 1", "Artificial Intelligence", "BEGINNER", ["ai"], "10.00")
    c2 = make_course("Adv Course 2", "Artificial Intelligence", "ADVANCED", ["ai"], "90.00")
    db_session.add_all([c1, c2])
    await db_session.commit()

    path = make_path(user_id=regular_user.id, primary_domain="RAG", course_count=1, total_price=Decimal("10.00"))
    db_session.add(path)
    await db_session.flush()

    item = LearningPathItem(learning_path_id=path.id, course_id=c1.id, position=1, stage_label="Stage 1", reason="Reason", how_it_prepares_next="Outcome", estimated_hours=3, price_snapshot=Decimal("10.00"), currency="USD")
    db_session.add(item)
    await db_session.commit()

    loaded_path = await get_owned_path(db_session, regular_user.id, path.id)
    target_item = loaded_path.items[0]

    result = await replace_item(db_session, loaded_path, target_item, reason="TOO_ADVANCED", trace_id="test_too_advanced")
    assert result.replaced is False
    assert result.reason_code == "NO_EASIER_CANDIDATE"
    assert result.user_message == "No easier grounded replacement is available for this stage."


@pytest.mark.asyncio
async def test_replace_item_no_grounded_candidates(db_session, regular_user):
    c1 = make_course("Sole Course 1", "Unique Domain", "BEGINNER", ["unique"], "10.00")
    db_session.add(c1)
    await db_session.commit()

    path = make_path(user_id=regular_user.id, primary_domain="FRONTEND", course_count=3, total_price=Decimal("10.00"))
    db_session.add(path)
    await db_session.flush()

    item = LearningPathItem(
        learning_path_id=path.id,
        course_id=c1.id,
        position=1,
        stage_label="Stage 1",
        reason="Initial",
        how_it_prepares_next="Outcome",
        skills_gained_json=["unique"],
        estimated_hours=1,
        price_snapshot=Decimal("10.00"),
        currency="USD",
    )
    db_session.add(item)
    await db_session.commit()

    loaded_path = await get_owned_path(db_session, regular_user.id, path.id)
    target_item = loaded_path.items[0]

    result = await replace_item(db_session, loaded_path, target_item, reason="PREFER_TOPIC", trace_id="test_trace_no_candidates")
    assert result.replaced is False
    assert target_item.course_id == c1.id


@pytest.mark.asyncio
async def test_replace_item_route_commit_rollback(client, regular_user, db_session, sample_courses):
    login_page = await client.get("/login")
    login_csrf = csrf(login_page.text)
    await client.post(
        "/login",
        data={"email": regular_user.email, "password": "StudentPass123!", "csrf_token": login_csrf},
    )

    c1, c2, c3 = sample_courses[0], sample_courses[1], sample_courses[2]
    path = make_path(user_id=regular_user.id, primary_domain="AGENTIC_AI", course_count=3, total_price=c1.price + c2.price + c3.price)
    db_session.add(path)
    await db_session.flush()

    item1 = LearningPathItem(
        learning_path_id=path.id, course_id=c1.id, position=1, stage_label="Build the foundation",
        reason="Base", how_it_prepares_next=f"This stage prepares you for {c2.title}.",
        skills_gained_json=c1.tags, estimated_hours=3, price_snapshot=c1.price, currency="USD",
    )
    item2 = LearningPathItem(
        learning_path_id=path.id, course_id=c2.id, position=2, stage_label="Apply the skill",
        reason="Core", how_it_prepares_next=f"This stage prepares you for {c3.title}.",
        skills_gained_json=c2.tags, estimated_hours=3, price_snapshot=c2.price, currency="USD",
    )
    item3 = LearningPathItem(
        learning_path_id=path.id, course_id=c3.id, position=3, stage_label="Master",
        reason="Advanced", how_it_prepares_next="Outcome",
        skills_gained_json=c3.tags, estimated_hours=3, price_snapshot=c3.price, currency="USD",
    )
    db_session.add_all([item1, item2, item3])
    await db_session.commit()

    detail_page = await client.get(f"/learning-paths/{path.id}")
    path_csrf = csrf(detail_page.text)

    with patch("app.routers.learning_paths._record_path_event", side_effect=Exception("Event commit error")):
        response = await client.post(
            f"/learning-paths/{path.id}/items/{item1.id}/replace",
            data={"reason": "PREFER_TOPIC", "csrf_token": path_csrf},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == f"/learning-paths/{path.id}"
