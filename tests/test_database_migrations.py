import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.database import run_migrations


@pytest.mark.asyncio
async def test_startup_migrations_create_enrollments(tmp_path, monkeypatch):
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'migration-test.db'}"
    monkeypatch.setattr(settings, "database_url", database_url)

    await run_migrations()

    engine = create_async_engine(database_url)
    async with engine.connect() as connection:
        tables = await connection.run_sync(lambda sync_connection: inspect(sync_connection).get_table_names())
        revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
    await engine.dispose()

    assert "enrollments" in tables
    assert revision == "0012_expand_learning_path_status"
