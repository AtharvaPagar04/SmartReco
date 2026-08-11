import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy import select

import resend
from app.config import settings, Settings, validate_runtime_configuration, get_settings
from app.models import (
    ActivityEvent,
    Course,
    RecommendationDelivery,
    RecommendationItem,
    RecommendationPreference,
    RecommendationRun,
    SessionFollowupState,
    User,
)
from app.services.recommendation_email_service import (
    ConsoleEmailProvider,
    ResendEmailProvider,
    SMTPEmailProvider,
    DeliveryResult,
    email_provider,
)
from app.jobs.recommendation_jobs import process_email_deliveries


def _utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_email_provider_factory_selection(monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "console")
    assert isinstance(email_provider(), ConsoleEmailProvider)

    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_username", "user")
    monkeypatch.setattr(settings, "smtp_password", "pass")
    monkeypatch.setattr(settings, "email_from_address", "noreply@example.com")
    assert isinstance(email_provider(), SMTPEmailProvider)

    monkeypatch.setattr(settings, "email_provider", "resend")
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key_123")
    monkeypatch.setattr(settings, "email_from_address", "SmartReco <onboarding@resend.dev>")
    assert isinstance(email_provider(), ResendEmailProvider)


def test_unknown_email_provider_fails(monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "unknown_provider")
    with pytest.raises(ValueError, match="Unsupported EMAIL_PROVIDER|Invalid EMAIL_PROVIDER"):
        email_provider()


def test_missing_resend_api_key_raises_config_error(monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "resend")
    monkeypatch.setattr(settings, "resend_api_key", "")
    monkeypatch.setattr(settings, "email_from_address", "SmartReco <onboarding@resend.dev>")
    with pytest.raises(ValueError, match="RESEND_API_KEY"):
        validate_runtime_configuration(settings)
    with pytest.raises(ValueError, match="RESEND_API_KEY"):
        email_provider()


def test_missing_email_from_raises_config_error(monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "resend")
    monkeypatch.setattr(settings, "resend_api_key", "re_test_123")
    monkeypatch.setattr(settings, "email_from_address", "")
    with pytest.raises(ValueError, match="EMAIL_FROM_ADDRESS"):
        validate_runtime_configuration(settings)
    with pytest.raises(ValueError, match="EMAIL_FROM_ADDRESS"):
        email_provider()


@pytest.mark.asyncio
async def test_resend_provider_sends_correct_payload(monkeypatch):
    provider = ResendEmailProvider(api_key="re_secret_key_999", from_address="SmartReco <onboarding@resend.dev>")

    with patch("resend.Emails.send") as mock_send:
        mock_send.return_value = {"id": "msg_resend_999"}
        result = await provider.send_recommendation_digest(
            recipient="learner@example.com",
            subject="Personalized Course Recommendations",
            text="Hello Learner, check these courses out.",
            html="<h1>Hello Learner</h1><p>check these courses out.</p>",
        )

        assert result.success is True
        assert result.message_id == "msg_resend_999"
        mock_send.assert_called_once_with(
            {
                "from": "SmartReco <onboarding@resend.dev>",
                "to": "learner@example.com",
                "subject": "Personalized Course Recommendations",
                "html": "<h1>Hello Learner</h1><p>check these courses out.</p>",
                "text": "Hello Learner, check these courses out.",
            }
        )


@pytest.mark.asyncio
async def test_resend_provider_handles_permanent_and_retryable_errors():
    provider = ResendEmailProvider(api_key="re_secret_key_999", from_address="SmartReco <onboarding@resend.dev>")

    # 401 Unauthorized -> Permanent failure
    with patch("resend.Emails.send") as mock_send:
        exc = resend.exceptions.ResendError(code=401, error_type="invalid_api_key", message="Invalid API key", suggested_action="")
        mock_send.side_effect = exc
        res = await provider.send_recommendation_digest(
            recipient="test@example.com", subject="s", text="t", html="h"
        )
        assert res.success is False
        assert res.permanent is True
        assert "Invalid API key" in res.error

    # RateLimitError / 429 -> Transient failure (retryable)
    with patch("resend.Emails.send") as mock_send:
        exc = resend.exceptions.ResendError(code=429, error_type="rate_limit_exceeded", message="Rate limit exceeded", suggested_action="")
        mock_send.side_effect = exc
        res = await provider.send_recommendation_digest(
            recipient="test@example.com", subject="s", text="t", html="h"
        )
        assert res.success is False
        assert res.permanent is False

    # Connection error -> Transient failure
    with patch("resend.Emails.send") as mock_send:
        mock_send.side_effect = Exception("Connection timeout")
        res = await provider.send_recommendation_digest(
            recipient="test@example.com", subject="s", text="t", html="h"
        )
        assert res.success is False
        assert res.permanent is False


@pytest.mark.asyncio
async def test_process_email_deliveries_with_resend_success_and_retry_durability(db_session, regular_user, monkeypatch):
    secret_key = "re_super_secret_api_key_12345"
    monkeypatch.setattr(settings, "email_provider", "resend")
    monkeypatch.setattr(settings, "resend_api_key", secret_key)
    monkeypatch.setattr(settings, "email_from_address", "SmartReco <onboarding@resend.dev>")

    # Create dummy course & recommendation run
    course = Course(
        title="Async Python Development",
        slug="async-python-development",
        short_description="Master async Python.",
        description="Deep dive into asyncio.",
        category="Backend",
        tags=["python", "async"],
        price=0,
        currency="USD",
        difficulty="INTERMEDIATE",
        instructor="Jane Doe",
        duration_minutes=120,
        is_featured=True,
        is_active=True,
        version=1,
        vector_status="COMPLETED",
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)

    run = RecommendationRun(
        user_id=regular_user.id,
        profile_hash="hash_test_resend_123",
        trigger_type="SESSION_FOLLOWUP",
        source_session_id="sess_resend_test",
        headline="Recommended Courses",
        narrative="Based on your activity",
        status="SUCCEEDED",
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    item = RecommendationItem(
        run_id=run.id,
        user_id=regular_user.id,
        course_id=course.id,
        rank=1,
        deterministic_score=0.9,
        semantic_score=0.9,
        reason="Matches your search",
    )
    db_session.add(item)

    now = _utc_now()
    delivery = RecommendationDelivery(
        run_id=run.id,
        user_id=regular_user.id,
        recipient=regular_user.email,
        status="PENDING",
        scheduled_for=now,
    )
    db_session.add(delivery)
    await db_session.commit()
    await db_session.refresh(delivery)

    initial_run_count = len((await db_session.scalars(select(RecommendationRun))).all())

    # Step 1: Transient failure on first send attempt
    with patch("resend.Emails.send") as mock_send:
        mock_send.side_effect = Exception("Network glitch")
        await process_email_deliveries()

    await db_session.refresh(delivery)
    assert delivery.status == "PENDING"
    assert delivery.attempts == 1
    assert delivery.error_code == "email_delivery_failed"

    # Ensure no new RecommendationRun was generated
    run_count_after_retry = len((await db_session.scalars(select(RecommendationRun))).all())
    assert run_count_after_retry == initial_run_count

    # Step 2: Successful send attempt on retry
    delivery.scheduled_for = now  # Reset schedule so worker picks it up
    delivery.next_attempt_at = None
    await db_session.commit()

    with patch("resend.Emails.send") as mock_send:
        mock_send.return_value = {"id": "resend_msg_abc123"}
        await process_email_deliveries()

    await db_session.refresh(delivery)
    assert delivery.status == "SENT"
    assert delivery.attempts == 2
    assert delivery.provider_message_id == "resend_msg_abc123"

    # Ensure still no additional RecommendationRun created
    assert len((await db_session.scalars(select(RecommendationRun))).all()) == initial_run_count


@pytest.mark.asyncio
async def test_resend_does_not_log_api_key(caplog, monkeypatch):
    secret_key = "re_super_secret_api_key_NEVER_LOG_ME"
    monkeypatch.setattr(settings, "email_provider", "resend")
    monkeypatch.setattr(settings, "resend_api_key", secret_key)
    monkeypatch.setattr(settings, "email_from_address", "SmartReco <onboarding@resend.dev>")

    caplog.set_level(logging.DEBUG)

    provider = ResendEmailProvider(api_key=secret_key, from_address="SmartReco <onboarding@resend.dev>")

    with patch("resend.Emails.send") as mock_send:
        mock_send.return_value = {"id": "msg_secure_123"}
        await provider.send_recommendation_digest(
            recipient="test@example.com",
            subject="Sub",
            text="Txt",
            html="<p>Html</p>",
        )

    for record in caplog.records:
        assert secret_key not in record.getMessage()
        if hasattr(record, "extra") and record.extra:
            assert secret_key not in str(record.extra)
