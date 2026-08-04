import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.recommendation_graph import build_recommendation_graph
from app.services.recommendation_persistence_service import fail_run_in_fresh_session, start_run
from app.services.langsmith_service import trace_metadata, tracing_enabled
from app.config import settings

logger = logging.getLogger(__name__)


async def _cleanup_failed_run(run_id: str, code: str, message: str, *, cancelled: bool = False) -> None:
    task = asyncio.create_task(fail_run_in_fresh_session(run_id, code, message))
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        if cancelled:
            await task
        else:
            raise
    except Exception:
        logger.exception("recommendation run cleanup failed", extra={"run_id": run_id, "error_code": code})


async def generate_recommendation(db: AsyncSession, user_id: str, *, trigger_type: str = "BEHAVIOR_THRESHOLD", force: bool = False) -> tuple[str, str, dict | None]:
    run, decision, _profile = await start_run(db, user_id, trigger_type=trigger_type, force=force)
    if not run:
        return "SKIPPED", decision.reason, None
    graph = build_recommendation_graph(db)
    try:
        if tracing_enabled():
            try:
                from langsmith import trace
            except Exception:
                trace = None
            if trace:
                with trace(name="smartreco-recommendation", project_name=settings.langsmith_project, metadata=trace_metadata(user_id=user_id, trigger_type=trigger_type, profile_version=run.profile_version, candidate_count=0)) as span:
                    state = await graph.ainvoke({"run_id": run.id, "user_id": user_id, "trigger_type": trigger_type})
                    run.trace_id = str(getattr(span, "id", "")) or None
                    await db.commit()
            else:
                state = await graph.ainvoke({"run_id": run.id, "user_id": user_id, "trigger_type": trigger_type})
        else:
            state = await graph.ainvoke({"run_id": run.id, "user_id": user_id, "trigger_type": trigger_type})
    except asyncio.CancelledError:
        await _cleanup_failed_run(run.id, "run_interrupted", "Recommendation run was interrupted", cancelled=True)
        raise
    except Exception as exc:
        await _cleanup_failed_run(run.id, "recommendation_failed", "Recommendation generation failed")
        raise
    return "COMPLETED", run.id, state
