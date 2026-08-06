import pytest

from app.config import Settings, validate_runtime_configuration
from scripts.check_config import check_config


def test_production_validation_rejects_debug():
    s = Settings(
        app_env="production",
        debug=True,
        session_https_only=True,
        secret_key="a-very-secure-production-secret-key-12345",
        email_provider="smtp",
        smtp_host="smtp.example.com",
        smtp_username="user",
        smtp_password="pass",
        email_from_address="noreply@example.com",
    )
    with pytest.raises(ValueError, match="DEBUG mode must be disabled in production"):
        validate_runtime_configuration(s)


def test_production_validation_rejects_insecure_cookies():
    s = Settings(
        app_env="production",
        debug=False,
        session_https_only=False,
        secret_key="a-very-secure-production-secret-key-12345",
        email_provider="smtp",
        smtp_host="smtp.example.com",
        smtp_username="user",
        smtp_password="pass",
        email_from_address="noreply@example.com",
    )
    with pytest.raises(ValueError, match="SESSION_HTTPS_ONLY must be enabled in production"):
        validate_runtime_configuration(s)


def test_production_validation_rejects_placeholder_secret():
    s = Settings(
        app_env="production",
        debug=False,
        session_https_only=True,
        secret_key="development-only-change-me",
        email_provider="smtp",
        smtp_host="smtp.example.com",
        smtp_username="user",
        smtp_password="pass",
        email_from_address="noreply@example.com",
    )
    with pytest.raises(ValueError, match="SECRET_KEY must be changed in production"):
        validate_runtime_configuration(s)


def test_production_validation_rejects_console_email():
    s = Settings(
        app_env="production",
        debug=False,
        session_https_only=True,
        secret_key="a-very-secure-production-secret-key-12345",
        email_provider="console",
    )
    with pytest.raises(ValueError, match="EMAIL_PROVIDER must be configured for a production backend"):
        validate_runtime_configuration(s)


def test_remote_qdrant_requires_url():
    s = Settings(app_env="test", qdrant_mode="remote", qdrant_url="")
    with pytest.raises(ValueError, match="QDRANT_URL is required when QDRANT_MODE is set to 'remote'"):
        validate_runtime_configuration(s)


def test_local_qdrant_does_not_require_remote_url():
    s = Settings(app_env="test", qdrant_mode="local", qdrant_url="")
    validate_runtime_configuration(s)


def test_langsmith_enabled_requires_api_key():
    s = Settings(app_env="test", langsmith_tracing=True, langsmith_api_key="")
    with pytest.raises(ValueError, match="LANGSMITH_API_KEY is required when LANGSMITH_TRACING is enabled"):
        validate_runtime_configuration(s)


def test_google_auth_enabled_requires_credentials():
    s = Settings(app_env="test", google_auth_enabled=True, google_client_id="")
    with pytest.raises(ValueError, match="GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI are required"):
        validate_runtime_configuration(s)


def test_smtp_email_requires_credentials():
    s = Settings(app_env="test", email_provider="smtp", smtp_host="")
    with pytest.raises(ValueError, match="SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, and EMAIL_FROM_ADDRESS are required"):
        validate_runtime_configuration(s)


from app.config import get_settings


def test_check_config_does_not_print_secrets(capsys, monkeypatch):
    monkeypatch.setenv("MESH_API_KEY", "super-secret-mesh-key")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "super-secret-google-secret")
    get_settings.cache_clear()

    success = check_config()
    get_settings.cache_clear()

    assert success is True

    captured = capsys.readouterr()
    stdout_stderr = captured.out + captured.err
    assert "super-secret-mesh-key" not in stdout_stderr
    assert "super-secret-google-secret" not in stdout_stderr
    assert "API key configured: yes" in stdout_stderr
    assert "Client secret configured: yes" in stdout_stderr
