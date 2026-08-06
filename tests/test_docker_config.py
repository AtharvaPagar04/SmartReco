from pathlib import Path
import pytest

from app.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_contents():
    dockerfile = PROJECT_ROOT / "Dockerfile"
    assert dockerfile.exists(), "Dockerfile must exist"
    content = dockerfile.read_text()

    assert "python:3.11-slim" in content
    assert "USER smartreco" in content
    assert "COPY .env" not in content
    assert "alembic upgrade" not in content  # Migrations must run at startup, not image build
    assert "EXPOSE 8000" in content
    assert "scripts/start_production.sh" in content


def test_dockerignore_contents():
    dockerignore = PROJECT_ROOT / ".dockerignore"
    assert dockerignore.exists(), ".dockerignore must exist"
    content = dockerignore.read_text().splitlines()

    ignored = {line.strip() for line in content if line.strip() and not line.startswith("#")}
    assert ".env" in ignored
    assert ".venv" in ignored
    assert "*.db" in ignored
    assert "data/qdrant" in ignored


def test_start_production_script_contents():
    script = PROJECT_ROOT / "scripts" / "start_production.sh"
    assert script.exists(), "scripts/start_production.sh must exist"
    content = script.read_text()

    assert content.startswith("#!/usr/bin/env sh")
    assert "RUN_MIGRATIONS_ON_START" in content
    assert "SEED_ON_START" in content
    assert "exec uvicorn" in content
    assert "--host 0.0.0.0" in content
    assert "--port \"${PORT:-8000}\"" in content or "--port \"$PORT\"" in content or "PORT:-8000" in content
    assert "--reload" not in content
    assert "--workers" not in content


def test_production_postgresql_url_acceptance():
    s = Settings(database_url="postgresql://user:pass@host:5432/dbname")
    assert s.database_url == "postgresql+asyncpg://user:pass@host:5432/dbname"


    s_asyncpg = Settings(database_url="postgresql+asyncpg://user:pass@host:5432/dbname")
    assert s_asyncpg.database_url == "postgresql+asyncpg://user:pass@host:5432/dbname"
