import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings, validate_runtime_configuration
from app.config_loader import CONFIG_DIR


def check_config() -> bool:
    print("SmartReco configuration\n")

    app_env = os.getenv("APP_ENV", "development").lower()
    print(f"Environment: {app_env}")

    config_files = ["config/defaults.toml", f"config/{app_env}.toml"]
    if app_env == "development" and (CONFIG_DIR / "local.toml").exists():
        config_files.append("config/local.toml")

    print("Config files:")
    for file_path in config_files:
        exists_str = " (found)" if (Path(__file__).resolve().parents[1] / file_path).exists() else " (missing)"
        print(f"- {file_path}{exists_str}")

    try:
        settings = get_settings()
        validate_runtime_configuration(settings)
        valid = True
    except Exception as exc:
        print(f"\nConfiguration Error: {exc}", file=sys.stderr)
        valid = False

    try:
        settings = get_settings()
    except Exception as exc:
        print(f"\nFailed to load settings: {exc}", file=sys.stderr)
        return False

    print("\nCore:")
    print(f"- Database configured: {'yes' if settings.database_url else 'no'}")
    print(f"- Secret key configured: {'yes' if settings.secret_key else 'no'}")

    print("\nMesh:")
    mesh_enabled = bool(settings.mesh_api_key)
    print(f"- Enabled: {'yes' if mesh_enabled else 'no'}")
    print(f"- API key configured: {'yes' if settings.mesh_api_key else 'no'}")
    print(f"- Chat model: {settings.mesh_chat_model}")
    print(f"- Embedding model: {settings.mesh_embedding_model}")

    print("\nQdrant:")
    print(f"- Mode: {settings.qdrant_mode}")
    print(f"- Collection: {settings.qdrant_collection}")
    print(f"- Vector size: {settings.vector_size}")

    print("\nGoogle:")
    print(f"- Enabled: {'yes' if settings.google_auth_enabled else 'no'}")
    print(f"- Client ID configured: {'yes' if settings.google_client_id else 'no'}")
    print(f"- Client secret configured: {'yes' if settings.google_client_secret else 'no'}")
    print(f"- Redirect URI configured: {'yes' if settings.google_redirect_uri else 'no'}")

    print("\nEmail:")
    print(f"- Provider: {settings.email_provider}")
    if settings.email_provider == "resend":
        print(f"- API key configured: {'yes' if bool(settings.resend_api_key) else 'no'}")
        print(f"- From address configured: {'yes' if bool(settings.email_from_address) else 'no'}")
    elif settings.email_provider == "smtp":
        print(f"- SMTP host configured: {'yes' if bool(settings.smtp_host) else 'no'}")
        print(f"- From address configured: {'yes' if bool(settings.email_from_address) else 'no'}")

    print("\nLangSmith:")
    print(f"- Enabled: {'yes' if settings.langsmith_tracing else 'no'}")

    if not valid:
        print("\nResult: INVALID CONFIGURATION", file=sys.stderr)
        return False

    print("\nResult: VALID CONFIGURATION")
    return True


if __name__ == "__main__":
    success = check_config()
    sys.exit(0 if success else 1)
