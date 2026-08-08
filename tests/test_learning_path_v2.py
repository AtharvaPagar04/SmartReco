from decimal import Decimal
from uuid import uuid4

import pytest

from app.config import settings
from app.models import Course
from app.schemas.learning_path import LearningPathInput
from app.services.learning_path_intent import LearningPathIntent
from app.services.learning_path_planner import generate_plan_with_repairs, select_fallback_courses
from app.services.learning_path_policy import classify_course_for_path, classify_course_domain_affinity
from app.services.learning_path_validator import validate_learning_path_plan
from app.services.recommendation_retrieval_service import RecommendationCandidate


def make_course(title: str, category: str, difficulty: str = "INTERMEDIATE", tags: list[str] | None = None, price: int = 0) -> Course:
    tags = tags or []
    return Course(
        id=str(uuid4()), title=title, slug=str(uuid4()), short_description=title, description=title,
        category=category, tags=tags, price=Decimal(price), currency="USD", difficulty=difficulty,
        instructor="Instructor", duration_minutes=120, is_active=True, what_you_will_learn=tags,
        prerequisites=[], target_audience=[], tools_used=[], curriculum=[], final_project=None,
    )


def exact_input() -> LearningPathInput:
    return LearningPathInput(
        primary_domain="FRONTEND", secondary_domains=["UX"], goals=["PRODUCTION", "ADVANCED"],
        level="FAMILIAR", learning_preferences=["PRODUCTION"],
        prior_skills=["PYTHON", "GIT", "APIS", "PROMPT_ENGINEERING"],
        format_preferences=["PRACTICE", "PROJECTS"], weekly_hours=5, path_length="DEEP",
    )


def candidates() -> list[RecommendationCandidate]:
    courses = [
        make_course("Frontend React TypeScript Web Performance", "Web Development", tags=["frontend", "react", "typescript", "web performance", "production"]),
        make_course("Modern Frontend Browser Architecture", "Web Development", tags=["frontend", "browser", "javascript", "architecture"]),
        make_course("Responsive Frontend Interface Engineering", "Web Development", tags=["frontend", "responsive", "interface", "css"]),
        make_course("Production Frontend Applications", "Web Development", tags=["frontend", "production", "deployment", "javascript"]),
        make_course("Accessible Interface Design Systems", "UI/UX Design", tags=["accessibility", "interface", "design systems", "user experience"]),
        make_course("Interaction Design for Web Interfaces", "UI/UX Design", tags=["interaction", "design", "interface", "usability"]),
        make_course("Design Systems That Scale", "UI/UX Design", tags=["design systems", "components", "accessibility", "interface"]),
        make_course("Frontend Testing and Delivery", "Web Development", tags=["frontend", "browser", "production", "deployment"]),
        make_course("FastAPI Backend Development", "Web Development", tags=["fastapi", "backend", "python", "apis"]),
        make_course("Introduction to Agentic AI", "Agentic AI", tags=["agents", "prompt engineering", "ai"]),
    ]
    return [RecommendationCandidate(course=course, semantic_score=0.8) for course in courses]


def test_intent_preserves_all_goals_and_separates_known_skills():
    intent = LearningPathIntent.from_input(exact_input())
    assert intent.goal_codes == ("PRODUCTION", "ADVANCED")
    assert intent.prior_skill_codes == ("PYTHON", "GIT", "APIS", "PROMPT_ENGINEERING")
    assert intent.to_prompt_dict()["targets"]["goals"] == ["Build a production application", "Understand advanced concepts"]
    assert intent.to_prompt_dict()["known_skills"] == ["Python", "Git", "APIs", "Prompt Engineering"]


def test_taxonomy_collision_does_not_make_fastapi_frontend_primary():
    frontend = exact_input()
    fastapi = next(item.course for item in candidates() if item.course.title.startswith("FastAPI"))
    performance = next(item.course for item in candidates() if item.course.title.startswith("Frontend React"))
    role, _ = classify_course_for_path(fastapi, frontend.primary_domain, tuple(frontend.secondary_domains))
    assert classify_course_domain_affinity(fastapi, "FRONTEND").score < 0.50
    assert role == "OUT_OF_DOMAIN"
    assert classify_course_domain_affinity(performance, "FRONTEND").score >= 0.50


def test_fallback_meets_domain_composition_and_excludes_agentic_ai():
    intent = LearningPathIntent.from_input(exact_input())
    selected = select_fallback_courses(candidates(), intent, {})
    titles = [course.title for course in selected]
    assert len(selected) == 8
    assert "FastAPI Backend Development" not in titles
    assert "Introduction to Agentic AI" not in titles


def valid_plan(intent: LearningPathIntent | dict, items: list[RecommendationCandidate]) -> dict:
    stages = []
    goal_codes = list(intent.goal_codes) if hasattr(intent, "goal_codes") else list(intent.get("goal_codes", []))
    for position, item in enumerate(items[:8], 1):
        stages.append({
            "position": position, "course_id": item.course.id, "role": item.path_role or "PRIMARY",
            "goal_codes": goal_codes, "why_this_course": "Uses the grounded catalog metadata.",
            "goal_alignment": "Supports the selected goals.", "skill_gain": "Practical domain skills.",
            "how_it_leads_forward": "Builds toward the next grounded stage.",
        })
    return {"title": "Frontend and UX roadmap", "summary": "A grounded roadmap.", "final_outcome": "Ship a production interface.", "stages": stages}



@pytest.mark.asyncio
async def test_mesh_valid_plan_is_used_and_all_goals_reach_prompt(monkeypatch):
    intent = LearningPathIntent.from_input(exact_input())
    items = candidates()[:8]
    captured = {}

    async def fake_mesh(*, intent, candidates, repair=None):
        captured["intent"] = intent
        return valid_plan(LearningPathIntent.from_input(exact_input()), items)

    monkeypatch.setattr("app.services.learning_path_planner.generate_learning_path_json", fake_mesh)
    monkeypatch.setattr(settings, "learning_path_max_repairs", 1)
    result = await generate_plan_with_repairs(intent, items, {})
    assert result.llm_generation_used is True
    assert result.deterministic_fallback_used is False
    assert captured["intent"]["goal_codes"] == ["PRODUCTION", "ADVANCED"]
    assert len(result.plan.stages) == 8


@pytest.mark.asyncio
async def test_mesh_out_of_domain_plan_repairs_with_grounded_ids(monkeypatch):
    intent = LearningPathIntent.from_input(exact_input())
    items = candidates()
    calls = []

    async def fake_mesh(*, intent, candidates, repair=None):
        calls.append(repair)
        if repair is None:
            plan = valid_plan(LearningPathIntent.from_input(exact_input()), items[:7] + [items[-1]])
            return plan
        return valid_plan(LearningPathIntent.from_input(exact_input()), items[:8])

    monkeypatch.setattr("app.services.learning_path_planner.generate_learning_path_json", fake_mesh)
    result = await generate_plan_with_repairs(intent, items, {})
    assert result.llm_generation_used is True
    assert result.repair_count == 1
    assert calls[1]["violations"][0]["code"] == "OUT_OF_DOMAIN"


def test_validator_rejects_invented_course_ids_and_wrong_count():
    intent = LearningPathIntent.from_input(exact_input())
    ranked = candidates()[:8]
    plan = valid_plan(intent, ranked)
    plan["stages"] = plan["stages"][:-1]
    plan["stages"][0]["course_id"] = "invented-course-id"
    result = validate_learning_path_plan(plan, intent, ranked)
    assert {item.code for item in result.violations} >= {"COURSE_COUNT", "UNGROUNDED_COURSE"}


def scarce_candidates() -> list[RecommendationCandidate]:
    courses = [
        make_course("Frontend React TypeScript Web Performance", "Web Development", tags=["frontend", "react", "typescript", "web performance", "production"]),
        make_course("Modern Frontend Browser Architecture", "Web Development", tags=["frontend", "browser", "javascript", "architecture"]),
        make_course("Responsive Frontend Interface Engineering", "Web Development", tags=["frontend", "responsive", "interface", "css"]),
        make_course("Production Frontend Applications", "Web Development", tags=["frontend", "production", "deployment", "javascript"]),
        make_course("Accessible Interface Design Systems", "UI/UX Design", tags=["accessibility", "interface", "design systems", "user experience"]),
        make_course("Interaction Design for Web Interfaces", "UI/UX Design", tags=["interaction", "design", "interface", "usability"]),
        make_course("FastAPI Backend Development", "Web Development", tags=["fastapi", "backend", "python", "apis"]),
        make_course("Introduction to Agentic AI", "Agentic AI", tags=["agents", "prompt engineering", "ai"]),
    ]
    return [RecommendationCandidate(course=course, semantic_score=0.8) for course in courses]


def test_coverage_resolver_calculates_effective_target_count():
    from app.services.learning_path_policy import resolve_learning_path_coverage
    intent = LearningPathIntent.from_input(exact_input())
    items = scarce_candidates()
    coverage = resolve_learning_path_coverage(items, intent)

    assert coverage.requested_count == 8
    assert coverage.available_safe_count == 6
    assert coverage.effective_target_count == 6
    assert coverage.coverage_limited is True
    assert coverage.coverage_reason == "CATALOG_DOMAIN_COVERAGE"


@pytest.mark.asyncio
async def test_generate_plan_with_repairs_coverage_aware_6_courses(monkeypatch):
    intent = LearningPathIntent.from_input(exact_input())
    items = scarce_candidates()

    async def fake_mesh(*, intent, candidates, repair=None):
        safe_items = [c for c in items if c.course.category in ("Web Development", "UI/UX Design") and "FastAPI" not in c.course.title]
        return valid_plan(intent, safe_items[:6])

    monkeypatch.setattr("app.services.learning_path_planner.generate_learning_path_json", fake_mesh)
    result = await generate_plan_with_repairs(intent, items, {})

    assert result.llm_generation_used is True


    assert result.validation_status == "VALID_COVERAGE_LIMITED"
    assert result.coverage.effective_target_count == 6
    assert len(result.plan.stages) == 6


@pytest.mark.asyncio
async def test_deterministic_fallback_coverage_aware_6_courses_and_clean_copy(monkeypatch):
    from app.services.mesh_chat_service import MeshChatError
    intent = LearningPathIntent.from_input(exact_input())
    items = scarce_candidates()

    async def failing_mesh(*, intent, candidates, repair=None):
        raise MeshChatError("Mesh unavailable")

    monkeypatch.setattr("app.services.learning_path_planner.generate_learning_path_json", failing_mesh)
    result = await generate_plan_with_repairs(intent, items, {})

    assert result.llm_generation_used is False
    assert result.deterministic_fallback_used is True
    assert result.validation_status == "FALLBACK_COVERAGE_LIMITED"
    assert len(result.plan.stages) == 6

    for stage in result.plan.stages:
        assert "primary" not in stage.why_this_course.lower() or "roadmap" in stage.why_this_course.lower()
        assert "using the selected catalog sequence" not in stage.how_it_leads_forward


def test_validator_enforces_effective_target_count():
    intent = LearningPathIntent.from_input(exact_input())
    items = candidates()
    plan_8 = valid_plan(intent, items[:8])

    val_failed = validate_learning_path_plan(plan_8, intent, items, exact_count=True, effective_target_count=6)
    assert val_failed.valid is False
    assert any(v.code == "COURSE_COUNT" for v in val_failed.violations)

    plan_6 = valid_plan(intent, items[:6])
    val_passed = validate_learning_path_plan(plan_6, intent, items, exact_count=True, effective_target_count=6)
    assert val_passed.valid is True


@pytest.mark.asyncio
async def test_insufficient_coverage_when_fewer_than_3_safe_courses():
    intent = LearningPathIntent.from_input(exact_input())
    items = scarce_candidates()[:2]
    result = await generate_plan_with_repairs(intent, items, {})

    assert result.validation_status == "INSUFFICIENT_COVERAGE"
    assert result.coverage.effective_target_count < 3
    assert len(result.plan.stages) == 0


def test_learning_path_status_length_invariant():
    from app.models.learning_path import LearningPathStatus

    MAX_STATUS_LENGTH = 64
    for status in LearningPathStatus.ALL_STATUSES:
        assert len(status) <= MAX_STATUS_LENGTH, f"Status {status} exceeds {MAX_STATUS_LENGTH} chars"


def test_learning_path_orm_schema_length():
    from app.models.learning_path import LearningPath

    status_col = LearningPath.__table__.columns["status"]
    assert status_col.type.length == 64


@pytest.mark.asyncio
async def test_auto_path_coverage_target_resolution():
    from app.services.learning_path_policy import resolve_learning_path_coverage

    base_input = exact_input().model_dump(mode="json")
    base_input["path_length"] = "AUTO"
    path_input = LearningPathInput.model_validate(base_input)
    intent = LearningPathIntent.from_input(path_input)
    all_items = candidates()

    # safe = 8
    cov_8 = resolve_learning_path_coverage(all_items[:8], intent)
    assert cov_8.effective_target_count == 8

    # safe = 6
    cov_6 = resolve_learning_path_coverage(scarce_candidates()[:6], intent)
    assert cov_6.effective_target_count == 6

    # safe = 3
    cov_3 = resolve_learning_path_coverage(scarce_candidates()[:3], intent)
    assert cov_3.effective_target_count == 3

    # safe = 2
    cov_2 = resolve_learning_path_coverage(scarce_candidates()[:2], intent)
    assert cov_2.effective_target_count == 2
    assert cov_2.effective_target_count < 3


@pytest.mark.asyncio
async def test_insufficient_coverage_status_persistence(db_session, regular_user):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.learning_path import LearningPath, LearningPathStatus
    from app.services.learning_path_service import create_learning_path

    base_input = exact_input().model_dump(mode="json")
    base_input["primary_domain"] = "AUTH"
    base_input["secondary_domains"] = []
    path_input = LearningPathInput.model_validate(base_input)

    path = await create_learning_path(db_session, regular_user, path_input)
    await db_session.commit()

    assert path.status == LearningPathStatus.INSUFFICIENT_COVERAGE

    reloaded = await db_session.scalar(select(LearningPath).where(LearningPath.id == path.id).options(selectinload(LearningPath.items)))
    assert reloaded is not None
    assert reloaded.status == "INSUFFICIENT_COVERAGE"
    assert len(reloaded.items) == 0


def test_auto_target_resolution_matrix():
    from app.services.learning_path_policy import resolve_learning_path_coverage

    all_items = candidates()
    scarce = scarce_candidates()

    for requested in (4, 8):
        base = exact_input().model_dump(mode="json")
        base["path_length"] = "AUTO"
        base["requested_course_count"] = requested
        intent = LearningPathIntent.from_input(LearningPathInput.model_validate(base))

        # safe = 0
        cov0 = resolve_learning_path_coverage([], intent)
        assert cov0.effective_target_count == 0
        assert cov0.coverage_limited is True

        # safe = 2 (< 3)
        cov2 = resolve_learning_path_coverage(scarce[:2], intent)
        assert cov2.effective_target_count == 2
        assert cov2.coverage_limited is True

        # safe = 3
        cov3 = resolve_learning_path_coverage(scarce[:3], intent)
        assert cov3.effective_target_count == 3
        assert cov3.coverage_limited is False

        # safe = 6
        cov6 = resolve_learning_path_coverage(scarce[:6], intent)
        assert cov6.effective_target_count == 6
        assert cov6.coverage_limited is False

        # safe = 8
        cov8 = resolve_learning_path_coverage(all_items[:8], intent)
        assert cov8.effective_target_count == 8
        assert cov8.coverage_limited is False

        # safe = 12 -> max capped at 8
        cov12 = resolve_learning_path_coverage(all_items[:12], intent)
        assert cov12.effective_target_count == 8
        assert cov12.coverage_limited is False


def test_composition_policy_effective_count_mapping():
    from app.services.learning_path_policy import composition_policy, path_mode_for_effective_count

    assert path_mode_for_effective_count(3) == "FOCUSED"
    assert path_mode_for_effective_count(4) == "FOCUSED"
    assert path_mode_for_effective_count(5) == "BALANCED"
    assert path_mode_for_effective_count(6) == "BALANCED"
    assert path_mode_for_effective_count(7) == "BALANCED"
    assert path_mode_for_effective_count(8) == "EXTENDED"

    pol6 = composition_policy(path_mode_for_effective_count(6), has_secondary=True)
    assert pol6["min_primary"] == 3
    assert pol6["min_secondary"] == 1
    assert pol6["max_supporting"] == 1


def test_known_six_course_role_pass():
    intent = LearningPathIntent.from_input(exact_input())
    items = scarce_candidates()[:6]
    val = validate_learning_path_plan(valid_plan(intent, items), intent, items, exact_count=True, effective_target_count=6)
    assert val.valid is True


@pytest.mark.asyncio
async def test_mesh_success_auto_six_courses_becomes_ready(db_session, regular_user, monkeypatch):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.learning_path import LearningPath, LearningPathStatus
    from app.services.learning_path_service import create_learning_path

    base = exact_input().model_dump(mode="json")
    base["path_length"] = "AUTO"
    base["requested_course_count"] = 8
    path_input = LearningPathInput.model_validate(base)

    items = scarce_candidates()[:6]
    for candidate in items:
        db_session.add(candidate.course)
    await db_session.flush()

    intent = LearningPathIntent.from_input(path_input)

    async def mock_mesh(*args, **kwargs):
        return valid_plan(intent, items)

    async def mock_retrieve(*args, **kwargs):
        return (items, True, False, ["query"])

    monkeypatch.setattr("app.services.learning_path_planner.generate_learning_path_json", mock_mesh)
    monkeypatch.setattr("app.services.learning_path_service.retrieve_learning_path_candidates", mock_retrieve)

    path = await create_learning_path(db_session, regular_user, path_input)
    await db_session.commit()

    reloaded = await db_session.scalar(select(LearningPath).where(LearningPath.id == path.id).options(selectinload(LearningPath.items)))
    assert reloaded.status == LearningPathStatus.READY
    assert len(reloaded.items) == 6
    assert reloaded.used_fallback is False


@pytest.mark.asyncio
async def test_fallback_success_when_mesh_fails_becomes_ready(db_session, regular_user, monkeypatch):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.learning_path import LearningPath, LearningPathStatus
    from app.services.learning_path_service import create_learning_path

    base = exact_input().model_dump(mode="json")
    base["path_length"] = "AUTO"
    base["requested_course_count"] = 8
    path_input = LearningPathInput.model_validate(base)

    items = scarce_candidates()[:6]
    for candidate in items:
        db_session.add(candidate.course)
    await db_session.flush()

    async def mock_mesh_fail(*args, **kwargs):
        raise RuntimeError("Mesh timeout")

    async def mock_retrieve(*args, **kwargs):
        return (items, True, False, ["query"])

    monkeypatch.setattr("app.services.learning_path_planner.generate_learning_path_json", mock_mesh_fail)
    monkeypatch.setattr("app.services.learning_path_service.retrieve_learning_path_candidates", mock_retrieve)

    path = await create_learning_path(db_session, regular_user, path_input)
    await db_session.commit()

    reloaded = await db_session.scalar(select(LearningPath).where(LearningPath.id == path.id).options(selectinload(LearningPath.items)))
    assert reloaded.status == LearningPathStatus.READY
    assert len(reloaded.items) == 6
    assert reloaded.used_fallback is True


@pytest.mark.asyncio
async def test_failed_status_when_all_generation_paths_fail(db_session, regular_user, monkeypatch):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.learning_path import LearningPath, LearningPathStatus
    from app.services.learning_path_service import create_learning_path

    base = exact_input().model_dump(mode="json")
    base["path_length"] = "AUTO"
    path_input = LearningPathInput.model_validate(base)

    items = scarce_candidates()[:6]
    for candidate in items:
        db_session.add(candidate.course)
    await db_session.flush()

    async def mock_mesh_fail(*args, **kwargs):
        raise RuntimeError("Mesh timeout")

    async def mock_retrieve(*args, **kwargs):
        return (items, True, False, ["query"])

    monkeypatch.setattr("app.services.learning_path_planner.generate_learning_path_json", mock_mesh_fail)
    monkeypatch.setattr("app.services.learning_path_planner.select_fallback_courses", lambda *a, **kw: [])
    monkeypatch.setattr("app.services.learning_path_service.retrieve_learning_path_candidates", mock_retrieve)

    path = await create_learning_path(db_session, regular_user, path_input)
    await db_session.commit()

    reloaded = await db_session.scalar(select(LearningPath).where(LearningPath.id == path.id).options(selectinload(LearningPath.items)))
    assert reloaded.status == LearningPathStatus.FAILED
    assert len(reloaded.items) == 0


@pytest.mark.asyncio
async def test_mesh_observability_timeout_fallback_succeeds(db_session, regular_user, monkeypatch):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.learning_path import LearningPath, LearningPathStatus
    from app.services.learning_path_service import create_learning_path

    base = exact_input().model_dump(mode="json")
    base["path_length"] = "AUTO"
    path_input = LearningPathInput.model_validate(base)

    items = scarce_candidates()[:6]
    for candidate in items:
        db_session.add(candidate.course)
    await db_session.flush()

    async def mock_mesh_timeout(*args, **kwargs):
        raise TimeoutError("Mesh request timed out")

    async def mock_retrieve(*args, **kwargs):
        return (items, True, False, ["query"])

    monkeypatch.setattr("app.services.learning_path_planner.generate_learning_path_json", mock_mesh_timeout)
    monkeypatch.setattr("app.services.learning_path_service.retrieve_learning_path_candidates", mock_retrieve)

    path = await create_learning_path(db_session, regular_user, path_input)
    await db_session.commit()

    reloaded = await db_session.scalar(
        select(LearningPath).where(LearningPath.id == path.id).options(selectinload(LearningPath.generation_runs))
    )
    assert reloaded.status == LearningPathStatus.READY

    run = reloaded.generation_runs[0]
    meta = run.metadata_json
    assert meta["llm_attempted"] is True
    assert meta["llm_generation_used"] is False
    assert meta["llm_failure_reason"] == "MESH_TIMEOUT"
    assert meta["deterministic_fallback_used"] is True
    assert meta["failure_reason"] is None


@pytest.mark.asyncio
async def test_mesh_observability_pydantic_schema_error(db_session, regular_user, monkeypatch):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.learning_path import LearningPath, LearningPathStatus
    from app.services.learning_path_service import create_learning_path

    base = exact_input().model_dump(mode="json")
    base["path_length"] = "AUTO"
    path_input = LearningPathInput.model_validate(base)

    items = scarce_candidates()[:6]
    for candidate in items:
        db_session.add(candidate.course)
    await db_session.flush()

    async def mock_mesh_invalid_schema(*args, **kwargs):
        return {"invalid_key": "not a plan"}

    async def mock_retrieve(*args, **kwargs):
        return (items, True, False, ["query"])

    monkeypatch.setattr("app.services.learning_path_planner.generate_learning_path_json", mock_mesh_invalid_schema)
    monkeypatch.setattr("app.services.learning_path_service.retrieve_learning_path_candidates", mock_retrieve)

    path = await create_learning_path(db_session, regular_user, path_input)
    await db_session.commit()

    reloaded = await db_session.scalar(
        select(LearningPath).where(LearningPath.id == path.id).options(selectinload(LearningPath.generation_runs))
    )
    assert reloaded.status == LearningPathStatus.READY

    run = reloaded.generation_runs[0]
    meta = run.metadata_json
    assert meta["llm_attempted"] is True
    assert meta["llm_generation_used"] is False
    assert meta["llm_failure_reason"] == "MESH_SCHEMA_VALIDATION_ERROR"
    assert meta["deterministic_fallback_used"] is True


@pytest.mark.asyncio
async def test_mesh_observability_valid_mesh_result(db_session, regular_user, monkeypatch):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.learning_path import LearningPath, LearningPathStatus
    from app.services.learning_path_service import create_learning_path

    base = exact_input().model_dump(mode="json")
    base["path_length"] = "AUTO"
    path_input = LearningPathInput.model_validate(base)

    items = scarce_candidates()[:6]
    for candidate in items:
        db_session.add(candidate.course)
    await db_session.flush()

    intent = LearningPathIntent.from_input(path_input)

    async def mock_mesh_valid(*args, **kwargs):
        return valid_plan(intent, items)

    async def mock_retrieve(*args, **kwargs):
        return (items, True, False, ["query"])

    monkeypatch.setattr("app.services.learning_path_planner.generate_learning_path_json", mock_mesh_valid)
    monkeypatch.setattr("app.services.learning_path_service.retrieve_learning_path_candidates", mock_retrieve)

    path = await create_learning_path(db_session, regular_user, path_input)
    await db_session.commit()

    reloaded = await db_session.scalar(
        select(LearningPath).where(LearningPath.id == path.id).options(selectinload(LearningPath.generation_runs))
    )
    assert reloaded.status == LearningPathStatus.READY

    run = reloaded.generation_runs[0]
    meta = run.metadata_json
    assert meta["llm_attempted"] is True
    assert meta["llm_generation_used"] is True
    assert meta["llm_failure_reason"] is None
    assert meta["deterministic_fallback_used"] is False


@pytest.mark.asyncio
async def test_mesh_candidate_limit_never_exceeded(monkeypatch):
    intent = LearningPathIntent.from_input(exact_input())
    many_candidates = []
    for i in range(25):
        cat = "UI/UX Design" if i % 3 == 0 else "Web Development"
        c = make_course(f"Course {i}", cat, tags=["frontend", "design systems" if cat == "UI/UX Design" else "javascript"])
        cand = RecommendationCandidate(course=c, semantic_score=0.8)
        cand.path_role = "SECONDARY" if cat == "UI/UX Design" else "PRIMARY"
        many_candidates.append(cand)

    captured_prompt_candidates = []

    async def mock_mesh(*, intent, candidates, repair=None):
        nonlocal captured_prompt_candidates
        captured_prompt_candidates = candidates
        return valid_plan(intent, many_candidates[:8])

    monkeypatch.setattr("app.services.learning_path_planner.generate_learning_path_json", mock_mesh)
    monkeypatch.setattr(settings, "learning_path_max_candidates", 16)

    result = await generate_plan_with_repairs(intent, many_candidates, {})
    assert result.prompt_candidate_count == 16
    assert len(captured_prompt_candidates) == 16
