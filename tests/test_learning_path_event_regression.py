import inspect
import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import ActivityEvent, LearningPath, LearningPathGenerationRun
from app.routers.learning_paths import _record_path_event
from tests.conftest import csrf


@pytest.mark.asyncio
async def test_record_path_event_helper_signature_uses_primitives_not_orm_object():
    sig = inspect.signature(_record_path_event)
    params = list(sig.parameters.keys())
    assert "path" not in params
    assert "path_id" in params
    assert "primary_domain" in params
    assert "goal_code" in params
    assert "course_count" in params


@pytest.mark.asyncio
async def test_post_path_generation_flow(client, db_session, regular_user, course, monkeypatch):
    from app.models import Course
    c2 = Course(id="c2", title="Python Data Structures", slug="python-ds", short_description="Data structures", description="Data structures in python", category="Python", tags=["python"], price=0, currency="USD", difficulty="BEGINNER", instructor="Inst", duration_minutes=60, is_active=True)
    c3 = Course(id="c3", title="Python Web Development", slug="python-web", short_description="Web dev", description="Web dev in python", category="Python", tags=["python"], price=0, currency="USD", difficulty="BEGINNER", instructor="Inst", duration_minutes=60, is_active=True)
    db_session.add_all([c2, c3])
    await db_session.flush()

    monkeypatch.setattr("app.config.settings.mesh_api_key", "")

    # Log in user
    resp = await client.get("/login")
    login_csrf = csrf(resp.text)
    await client.post(
        "/login",
        data={"email": regular_user.email, "password": "StudentPass123!", "csrf_token": login_csrf},
    )

    # Get path builder page to retrieve CSRF token
    resp = await client.get("/path-builder")
    builder_csrf = csrf(resp.text)

    # 1 & 6: POST path generation does not raise MissingGreenlet and returns 303
    gen_resp = await client.post(
        "/path-builder/generate",
        data={
            "primary_domain": "PYTHON",
            "goals": ["PROJECTS"],
            "level": "BEGINNER",
            "weekly_hours": "5",
            "budget_type": "FLEXIBLE",
            "budget_scope": "PATH",
            "path_length": "AUTO",
            "csrf_token": builder_csrf,
        },
        follow_redirects=False,
    )
    assert gen_resp.status_code == 303
    location = gen_resp.headers.get("location", "")
    assert location.startswith("/learning-paths/")
    path_id = location.split("/")[-1]

    # 4: The learning path remains persisted
    path = await db_session.scalar(
        select(LearningPath)
        .options(selectinload(LearningPath.items))
        .where(LearningPath.id == path_id)
    )
    assert path is not None
    assert path.user_id == regular_user.id
    assert path.primary_domain == "PYTHON"

    # 2: Event recording succeeds after path is committed
    events = list(
        (
            await db_session.scalars(
                select(ActivityEvent)
                .where(ActivityEvent.user_id == regular_user.id)
                .order_by(ActivityEvent.occurred_at.asc())
            )
        ).all()
    )
    event_types = [e.event_type for e in events]
    assert "LEARNING_PATH_GENERATED" in event_types
    assert "LEARNING_PATH_SAVED" in event_types

    gen_event = next(e for e in events if e.event_type == "LEARNING_PATH_GENERATED")
    assert gen_event.metadata_json["path_id"] == path_id
    assert gen_event.metadata_json["domain_code"] == "PYTHON"
    assert gen_event.metadata_json["goal_code"] == "PROJECTS"
    assert isinstance(gen_event.metadata_json["course_count"], int)

    # 5: Generation is queued/recorded only once per generation run
    runs = list(
        (
            await db_session.scalars(
                select(LearningPathGenerationRun).where(
                    LearningPathGenerationRun.learning_path_id == path_id
                )
            )
        ).all()
    )
    assert len(runs) == 1
    assert runs[0].status == "SUCCEEDED"


@pytest.mark.asyncio
async def test_record_path_event_does_not_trigger_lazy_load(db_session, regular_user):
    # Construct a bare LearningPath instance without attaching relationships
    path = LearningPath(
        user_id=regular_user.id,
        title="Bare Path",
        summary="Test bare path",
        status="READY",
        primary_domain="PYTHON",
        goal_code="PROJECTS",
        level_code="BEGINNER",
        weekly_hours=5,
        budget_type="FLEXIBLE",
        budget_scope="PATH",
        path_length_preference="AUTO",
    )
    db_session.add(path)
    await db_session.flush()

    class RequestDummy:
        session = {}

    # 3: No relationship lazy loading occurs when passing primitive parameters
    await _record_path_event(
        db_session,
        RequestDummy(),
        regular_user.id,
        "LEARNING_PATH_GENERATED",
        path_id=path.id,
        primary_domain=path.primary_domain,
        goal_code=path.goal_code,
        course_count=0,
    )

    event = await db_session.scalar(
        select(ActivityEvent).where(
            ActivityEvent.user_id == regular_user.id,
            ActivityEvent.event_type == "LEARNING_PATH_GENERATED",
        )
    )
    assert event is not None
    assert event.metadata_json["path_id"] == path.id
    assert event.metadata_json["course_count"] == 0
