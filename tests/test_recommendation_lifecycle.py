import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import openai
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import database as app_database
from app.config import settings
from app.models import RecommendationRun, RecommendationState
from app.services import recommendation_service
from app.services.recommendation_persistence_service import fail_run
from app.services.recommendation_retrieval_service import RecommendationCandidate
from app.services.recommendation_service import generate_recommendation
import scripts.generate_recommendation as generate_cli


def _mesh_candidate(course):
    return RecommendationCandidate(course=course, deterministic_score=0.5, evidence={"source": "test"})


async def _run_mesh_failure(db_session, regular_user, course, monkeypatch, failure):
    monkeypatch.setattr(settings, "mesh_api_key", "mesh-test-key")
    monkeypatch.setattr(settings, "mesh_chat_model", "mesh-test-model")

    async def fake_retrieve(*args, **kwargs):
        return [_mesh_candidate(course)], False, True

    async def fake_generate(*args, **kwargs):
        raise failure

    monkeypatch.setattr("app.agents.recommendation_graph.retrieve_candidates", fake_retrieve)
    monkeypatch.setattr("app.agents.recommendation_graph.generate_json", fake_generate)
    return await generate_recommendation(db_session, regular_user.id, force=True)


@pytest.mark.asyncio
async def test_api_timeout_persists_fallback_and_releases_lease(db_session, regular_user, course, monkeypatch):
    result = await _run_mesh_failure(
        db_session,
        regular_user,
        course,
        monkeypatch,
        openai.APITimeoutError(request=httpx.Request("POST", "https://mesh.test")),
    )
    run = await db_session.get(RecommendationRun, result[1])
    state = await db_session.get(RecommendationState, regular_user.id)
    assert run.status == "FALLBACK_SUCCEEDED"
    assert run.used_llm_fallback is True
    assert run.error_code == "mesh_provider_timeout"
    assert run.cache_key
    assert state.active_run_id is None
    assert state.lease_expires_at is None


@pytest.mark.asyncio
async def test_connection_error_transitions_to_fallback(db_session, regular_user, course, monkeypatch):
    result = await _run_mesh_failure(
        db_session,
        regular_user,
        course,
        monkeypatch,
        openai.APIConnectionError(request=httpx.Request("POST", "https://mesh.test")),
    )
    run = await db_session.get(RecommendationRun, result[1])
    assert run.status == "FALLBACK_SUCCEEDED"
    assert run.used_llm_fallback is True


@pytest.mark.asyncio
async def test_retryable_status_error_transitions_to_fallback(db_session, regular_user, course, monkeypatch):
    response = httpx.Response(503, request=httpx.Request("POST", "https://mesh.test"))
    result = await _run_mesh_failure(
        db_session,
        regular_user,
        course,
        monkeypatch,
        openai.APIStatusError("upstream failure", response=response, body={"secret": "must not persist"}),
    )
    run = await db_session.get(RecommendationRun, result[1])
    assert run.status == "FALLBACK_SUCCEEDED"
    assert run.error_code == "mesh_retryable_status"
    assert "secret" not in (run.error_message or "")


@pytest.mark.asyncio
async def test_total_mesh_timeout_transitions_to_fallback(db_session, regular_user, course, monkeypatch):
    monkeypatch.setattr(settings, "mesh_api_key", "mesh-test-key")
    monkeypatch.setattr(settings, "mesh_chat_model", "mesh-test-model")
    monkeypatch.setattr(settings, "mesh_total_budget_seconds", 0.01)

    async def fake_retrieve(*args, **kwargs):
        return [_mesh_candidate(course)], False, True

    async def slow_generate(*args, **kwargs):
        await asyncio.sleep(1)

    monkeypatch.setattr("app.agents.recommendation_graph.retrieve_candidates", fake_retrieve)
    monkeypatch.setattr("app.agents.recommendation_graph.generate_json", slow_generate)
    result = await generate_recommendation(db_session, regular_user.id, force=True)
    run = await db_session.get(RecommendationRun, result[1])
    state = await db_session.get(RecommendationState, regular_user.id)
    assert run.status == "FALLBACK_SUCCEEDED"
    assert run.error_code == "mesh_total_timeout"
    assert state.active_run_id is None
    assert state.lease_expires_at is None


@pytest.mark.asyncio
async def test_cancelled_run_is_failed_and_cleanup_uses_fresh_session(db_session, regular_user, monkeypatch):
    user_id = regular_user.id
    previous = RecommendationRun(user_id=user_id, profile_hash="p" * 64, trigger_type="TEST", status="SUCCEEDED", completed_at=datetime.now(timezone.utc).replace(tzinfo=None))
    db_session.add(previous)
    await db_session.commit()
    started = asyncio.Event()

    class BlockingGraph:
        async def ainvoke(self, state):
            started.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(recommendation_service, "build_recommendation_graph", lambda db: BlockingGraph())
    cleanup_sessions = []
    original_maker = app_database.async_session_maker

    def tracking_maker(*args, **kwargs):
        session = original_maker(*args, **kwargs)
        cleanup_sessions.append(session)
        return session

    monkeypatch.setattr(app_database, "async_session_maker", tracking_maker)
    task = asyncio.create_task(generate_recommendation(db_session, user_id, force=True))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    db_session.expire_all()
    run = await db_session.scalar(select(RecommendationRun).where(RecommendationRun.user_id == user_id).order_by(RecommendationRun.created_at.desc()))
    state = await db_session.get(RecommendationState, user_id)
    assert cleanup_sessions
    assert run.status == "FAILED"
    assert run.error_code == "run_interrupted"
    assert run.completed_at is not None
    assert state.active_run_id is None
    assert state.lease_expires_at is None
    assert (await db_session.get(RecommendationRun, previous.id)).status == "SUCCEEDED"


@pytest.mark.asyncio
async def test_unexpected_graph_error_is_finalized(db_session, regular_user, monkeypatch):
    user_id = regular_user.id
    class BrokenGraph:
        async def ainvoke(self, state):
            raise RuntimeError("provider body must not be stored")

    monkeypatch.setattr(recommendation_service, "build_recommendation_graph", lambda db: BrokenGraph())
    with pytest.raises(RuntimeError):
        await generate_recommendation(db_session, user_id, force=True)
    db_session.expire_all()
    run = await db_session.scalar(select(RecommendationRun).where(RecommendationRun.user_id == user_id))
    state = await db_session.get(RecommendationState, user_id)
    assert run.status == "FAILED"
    assert run.error_code == "recommendation_failed"
    assert run.error_message == "Recommendation generation failed"
    assert state.active_run_id is None
    assert state.lease_expires_at is None


@pytest.mark.asyncio
async def test_cleanup_cannot_clear_another_run_and_is_idempotent(db_session, regular_user):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    old_id, newer_id = str(uuid4()), str(uuid4())
    db_session.add_all([
        RecommendationRun(id=old_id, user_id=regular_user.id, profile_hash="a" * 64, trigger_type="TEST", status="RUNNING", started_at=now),
        RecommendationRun(id=newer_id, user_id=regular_user.id, profile_hash="b" * 64, trigger_type="TEST", status="RUNNING", started_at=now),
        RecommendationState(user_id=regular_user.id, active_run_id=newer_id, lease_expires_at=now),
    ])
    await db_session.commit()
    await fail_run(db_session, old_id, "recommendation_failed", "untrusted error")
    state = await db_session.get(RecommendationState, regular_user.id)
    old_run = await db_session.get(RecommendationRun, old_id)
    completed_at = old_run.completed_at
    assert state.active_run_id == newer_id
    await fail_run(db_session, old_id, "recommendation_failed", "untrusted error")
    await db_session.refresh(old_run)
    assert old_run.completed_at == completed_at
    assert (await db_session.get(RecommendationState, regular_user.id)).active_run_id == newer_id


@pytest.mark.asyncio
async def test_successful_mesh_call_reports_llm_called(db_session, regular_user, course, monkeypatch):
    monkeypatch.setattr(settings, "mesh_api_key", "mesh-test-key")
    monkeypatch.setattr(settings, "mesh_chat_model", "mesh-test-model")

    async def fake_retrieve(*args, **kwargs):
        return [_mesh_candidate(course)], False, True

    async def fake_generate(*args, **kwargs):
        return {"headline": "A useful next step", "narrative": "This is a grounded explanation based on your recent course activity and the supplied catalog evidence.", "recommendations": [{"course_id": course.id, "reason": "This course matches the validated course evidence.", "cta_label": "Explore"}]}

    monkeypatch.setattr("app.agents.recommendation_graph.retrieve_candidates", fake_retrieve)
    monkeypatch.setattr("app.agents.recommendation_graph.generate_json", fake_generate)
    _, _, state = await generate_recommendation(db_session, regular_user.id, force=True)
    assert state["llm_called"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "reference", "state"),
    [("SKIPPED", "RUN_ALREADY_ACTIVE", None), ("COMPLETED", "REUSED", {"llm_called": False})],
)
async def test_cli_reports_actual_llm_usage(db_session, regular_user, monkeypatch, capsys, status, reference, state):
    user_id = regular_user.id
    monkeypatch.setattr(settings, "mesh_api_key", "mesh-test-key")
    monkeypatch.setattr(settings, "mesh_chat_model", "mesh-test-model")
    monkeypatch.setattr(generate_cli, "async_session_maker", async_sessionmaker(db_session.bind, expire_on_commit=False))
    async def fake_profile(*args, **kwargs):
        return SimpleNamespace(profile_json={})

    monkeypatch.setattr(generate_cli, "build_or_refresh_profile", fake_profile)

    async def fake_retrieve(*args, **kwargs):
        return [], False, True

    monkeypatch.setattr(generate_cli, "retrieve_candidates", fake_retrieve)
    monkeypatch.setattr(generate_cli, "rank_candidates", lambda *args, **kwargs: [])

    async def fake_generate(*args, **kwargs):
        return status, reference, state

    monkeypatch.setattr(generate_cli, "generate_recommendation", fake_generate)
    await generate_cli.main(SimpleNamespace(user_id=user_id, trigger="CLI", force=False, dry_run=False, no_llm=False, show_profile=False, show_candidates=False))
    payload = __import__("json").loads(capsys.readouterr().out)
    assert payload["llm_enabled"] is True
    assert payload["llm_called"] is False
    assert payload["llm"] is False
