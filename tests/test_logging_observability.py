import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

from app.services.learning_path_logging import (
    LearningPathTraceContext,
    log_learning_path_step,
    sanitize_log_value,
    _sanitize_log_message,
)
from app.schemas.learning_path import LearningPathInput
from app.services.learning_path_intent import LearningPathIntent
from app.services.recommendation_retrieval_service import RecommendationCandidate
from app.models import Course


def test_secret_redaction_strings_and_structures():
    """Verify that sensitive values and key names are properly redacted."""
    # Test secret values in strings
    assert sanitize_log_value("mesh_sec_1234567890abcdef12345678") == "[REDACTED_API_KEY]"
    assert sanitize_log_value("Bearer secret_jwt_token_12345") == "Bearer [REDACTED_API_KEY]"
    assert sanitize_log_value("sk-1234567890abcdef12345678") == "[REDACTED_API_KEY]"

    # Test dicts with secret keys
    sensitive_dict = {
        "mesh_api_key": "secret_key_val",
        "authorization": "Bearer token123",
        "normal_key": "safe_val",
        "nested": {
            "password": "p@ssword123",
            "secret": "shhh",
            "data": "public",
        },
    }
    sanitized_dict = sanitize_log_value(sensitive_dict)
    assert sanitized_dict["mesh_api_key"] == "[REDACTED]"
    assert sanitized_dict["authorization"] == "[REDACTED]"
    assert sanitized_dict["normal_key"] == "safe_val"
    assert sanitized_dict["nested"]["password"] == "[REDACTED]"
    assert sanitized_dict["nested"]["secret"] == "[REDACTED]"
    assert sanitized_dict["nested"]["data"] == "public"

    # Test lists and tuples
    sensitive_list = ["safe", "mesh_sec_1234567890abcdef12345678", {"api_key": "xyz"}]
    sanitized_list = sanitize_log_value(sensitive_list)
    assert sanitized_list[0] == "safe"
    assert sanitized_list[1] == "[REDACTED_API_KEY]"
    assert sanitized_list[2]["api_key"] == "[REDACTED]"

    # Test helper function string output
    msg = _sanitize_log_message("User auth header: Bearer mesh_sec_9999999999999999999999")
    assert "mesh_sec" not in msg
    assert "[REDACTED_API_KEY]" in msg


def test_trace_context_failure_recording():
    """Verify first and final failure stage tracking in LearningPathTraceContext."""
    ctx = LearningPathTraceContext(trace_id="test_trace_123")
    assert ctx.first_failure_stage is None
    assert ctx.first_failure_reason is None
    assert ctx.final_failure_stage is None
    assert ctx.final_failure_reason is None

    # Record first failure
    ctx.record_failure("planner.mesh", "MESH_TIMEOUT")
    assert ctx.first_failure_stage == "planner.mesh"
    assert ctx.first_failure_reason == "MESH_TIMEOUT"
    assert ctx.final_failure_stage == "planner.mesh"
    assert ctx.final_failure_reason == "MESH_TIMEOUT"

    # Record second failure
    ctx.record_failure("fallback.validation", "FALLBACK_FAILED")
    # First failure stage should remain unchanged
    assert ctx.first_failure_stage == "planner.mesh"
    assert ctx.first_failure_reason == "MESH_TIMEOUT"
    # Final failure stage should update to second failure
    assert ctx.final_failure_stage == "fallback.validation"
    assert ctx.final_failure_reason == "FALLBACK_FAILED"


def test_log_learning_path_step(caplog):
    """Verify log_learning_path_step formats and redacts parameters correctly."""
    caplog.set_level(logging.INFO)
    logger = logging.getLogger("test_logger")

    log_learning_path_step(
        logger,
        "learning_path.step.success",
        "trace_999",
        step="test_step",
        duration_ms=42.5,
        secret_param="mesh_sec_1234567890abcdef12345678",
        public_param="hello",
    )

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.message.startswith("learning_path.step.success")
    assert "trace_id=trace_999" in record.message
    assert "step=test_step" in record.message
    assert "duration_ms=42.5" in record.message
    assert "public_param=hello" in record.message
    assert "mesh_sec" not in record.message
    assert "[REDACTED_API_KEY]" in record.message


@pytest.mark.asyncio
async def test_retrieval_and_planner_logging(caplog):
    """Test trace propagation and log outputs during candidate retrieval and planning."""
    from app.logging_config import configure_logging
    configure_logging("INFO")
    app_logger = logging.getLogger("app")
    app_logger.addHandler(caplog.handler)
    ctx = LearningPathTraceContext(trace_id="pipeline_trace_001")

    path_input = LearningPathInput(
        primary_domain="FRONTEND",
        goals=["FUNDAMENTALS"],
        level="BEGINNER",
        weekly_hours=5,
    )
    intent = LearningPathIntent.from_input(path_input)
    profile = {"top_categories": [{"name": "Web Development"}]}

    c1 = Course(
        id="c1",
        title="Web Dev Basics",
        category="Web Development",
        price=Decimal("10.00"),
        duration_minutes=120,
        difficulty="BEGINNER",
        instructor="Test Instructor",
        slug="web-dev-basics",
        short_description="Frontend Basics",
        description="Full Frontend Basics",
        tags=["frontend", "react", "javascript"],
        what_you_will_learn=["React", "Frontend", "HTML"],
        is_active=True,
    )
    c2 = Course(
        id="c2",
        title="Advanced Web Dev",
        category="Web Development",
        price=Decimal("20.00"),
        duration_minutes=180,
        difficulty="INTERMEDIATE",
        instructor="Test Instructor",
        slug="advanced-web-dev",
        short_description="Advanced Frontend",
        description="Full Advanced Frontend",
        tags=["frontend", "typescript"],
        what_you_will_learn=["TypeScript", "Frontend", "UI"],
        is_active=True,
    )
    c3 = Course(
        id="c3",
        title="UI Components",
        category="Web Development",
        price=Decimal("15.00"),
        duration_minutes=150,
        difficulty="BEGINNER",
        instructor="Test Instructor",
        slug="ui-components",
        short_description="UI Components",
        description="Full UI Components",
        tags=["frontend", "ui"],
        what_you_will_learn=["UI Components", "Frontend"],
        is_active=True,
    )
    candidates = [
        RecommendationCandidate(course=c1, semantic_score=0.9),
        RecommendationCandidate(course=c2, semantic_score=0.8),
        RecommendationCandidate(course=c3, semantic_score=0.7),
    ]

    from app.services.learning_path_planner import generate_plan_with_repairs

    with patch("app.services.learning_path_planner.generate_learning_path_json", new_callable=AsyncMock) as mock_mesh:
        mock_mesh.return_value = {
            "title": "Your Web Dev Path",
            "summary": "Learn web dev",
            "final_outcome": "Master web dev",
            "stages": [
                {
                    "position": 1,
                    "course_id": "c1",
                    "role": "PRIMARY",
                    "goal_codes": ["FUNDAMENTALS"],
                    "why_this_course": "Good start",
                    "goal_alignment": "Fits job goal",
                    "skill_gain": "HTML/CSS",
                    "how_it_leads_forward": "Leads to c2",
                },
                {
                    "position": 2,
                    "course_id": "c2",
                    "role": "PRIMARY",
                    "goal_codes": ["FUNDAMENTALS"],
                    "why_this_course": "Deep dive",
                    "goal_alignment": "Fits job goal",
                    "skill_gain": "JavaScript",
                    "how_it_leads_forward": "Leads to c3",
                },
                {
                    "position": 3,
                    "course_id": "c3",
                    "role": "PRIMARY",
                    "goal_codes": ["FUNDAMENTALS"],
                    "why_this_course": "UI Practice",
                    "goal_alignment": "Fits job goal",
                    "skill_gain": "UI Design",
                    "how_it_leads_forward": "Completes path",
                },
            ],
        }

        res = await generate_plan_with_repairs(intent, candidates, profile, trace_context=ctx)

        assert res.plan is not None
        messages = [r.message for r in caplog.records]
        assert any("step=candidates.prerank" in m and "trace_id=pipeline_trace_001" in m for m in messages)
        assert any("step=coverage.resolve" in m and "trace_id=pipeline_trace_001" in m for m in messages)
        assert any("step=domain.coverage" in m and "trace_id=pipeline_trace_001" in m for m in messages)
        assert any("step=planner.mesh" in m and "trace_id=pipeline_trace_001" in m for m in messages)
        assert any("step=planner.schema_validation" in m and "trace_id=pipeline_trace_001" in m for m in messages)
        assert any("step=planner.validation" in m and "trace_id=pipeline_trace_001" in m for m in messages)


def test_configure_logging_levels_and_handler():
    """Verify configure_logging explicitly sets app logger level and child effective levels."""
    from app.logging_config import configure_logging, SMARTRECO_HANDLER_NAME

    configure_logging("INFO")

    app_logger = logging.getLogger("app")
    assert app_logger.getEffectiveLevel() == logging.INFO
    assert app_logger.disabled is False
    assert app_logger.propagate is False

    child_logger1 = logging.getLogger("app.learning_path")
    assert child_logger1.getEffectiveLevel() == logging.INFO

    child_logger2 = logging.getLogger("app.services.learning_path_planner")
    assert child_logger2.getEffectiveLevel() == logging.INFO

    smartreco_handlers = [h for h in app_logger.handlers if getattr(h, "name", None) == SMARTRECO_HANDLER_NAME]
    assert len(smartreco_handlers) == 1

    configure_logging("INFO")
    smartreco_handlers = [h for h in app_logger.handlers if getattr(h, "name", None) == SMARTRECO_HANDLER_NAME]
    assert len(smartreco_handlers) == 1


def test_alembic_logging_config_interaction():
    """Verify Alembic fileConfig does not disable app logger or reset INFO level."""
    from logging.config import fileConfig
    from app.logging_config import configure_logging

    configure_logging("INFO")
    fileConfig("alembic.ini", disable_existing_loggers=False)

    app_logger = logging.getLogger("app")
    assert app_logger.disabled is False
    assert app_logger.getEffectiveLevel() == logging.INFO
    assert logging.getLogger("app.learning_path").getEffectiveLevel() == logging.INFO


def test_learning_path_step_emits_info_record(caplog):
    """Verify log_learning_path_step emits INFO level records through app logger hierarchy."""
    from app.logging_config import configure_logging

    configure_logging("INFO")
    app_logger = logging.getLogger("app")
    app_logger.addHandler(caplog.handler)
    caplog.set_level(logging.INFO)

    lp_logger = logging.getLogger("app.learning_path")
    log_learning_path_step(
        lp_logger,
        event="learning_path.step.success",
        trace_id="test-trace-info",
        step="coverage.resolve",
    )

    messages = [r.message for r in caplog.records]
    assert any("learning_path.step.success" in m and "trace_id=test-trace-info" in m and "step=coverage.resolve" in m for m in messages)
