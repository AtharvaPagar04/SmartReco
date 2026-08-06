import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_liveness_endpoint_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readiness_endpoint_returns_ready_when_db_ok():
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


def test_readiness_endpoint_returns_503_on_db_failure(monkeypatch):
    with patch("sqlalchemy.ext.asyncio.AsyncSession.execute", side_effect=Exception("Database connection error")):
        response = client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unavailable"
        assert data["database"] == "error"
        # Must not reveal connection details or stack traces
        assert "Database connection error" not in response.text
        assert "password" not in response.text
