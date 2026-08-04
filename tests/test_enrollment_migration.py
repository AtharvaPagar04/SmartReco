import asyncio
from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.models.enrollment import Enrollment


def get_alembic_config(db_url: str) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))
    return config


def test_enrollment_model_table_name_and_columns():
    assert Enrollment.__tablename__ == "enrollments"
    column_names = {c.name for c in Enrollment.__table__.columns}
    expected = {"id", "user_id", "course_id", "status", "started_at", "last_accessed_at", "completed_at", "created_at", "updated_at"}
    assert expected.issubset(column_names)


@pytest.mark.asyncio
async def test_fresh_database_migration(tmp_path, monkeypatch):
    db_path = tmp_path / "fresh_test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    monkeypatch.setattr(settings, "database_url", db_url)

    config = get_alembic_config(db_url)
    await asyncio.to_thread(command.upgrade, config, "head")

    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        columns = [c["name"] for c in await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_columns("enrollments"))]
        fks = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_foreign_keys("enrollments"))
        uqs = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_unique_constraints("enrollments"))
        rev = await conn.scalar(text("SELECT version_num FROM alembic_version"))

    await engine.dispose()

    assert "enrollments" in tables
    assert "status" in columns
    assert "completed_at" in columns
    assert len(fks) >= 2
    assert any(uq["name"] == "uq_enrollment_user_course" for uq in uqs)
    assert rev == "0007_recommendation_feedback"


@pytest.mark.asyncio
async def test_existing_schema_upgrade_preserves_data(tmp_path, monkeypatch):
    db_path = tmp_path / "upgrade_test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    monkeypatch.setattr(settings, "database_url", db_url)

    config = get_alembic_config(db_url)

    # Upgrade to 0003_recommendations
    await asyncio.to_thread(command.upgrade, config, "0003_recommendations")

    # Insert user and course data at 0003
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, full_name, email, password_hash, role, is_active) "
                "VALUES ('u1', 'Test User', 'user@test.com', 'hash', 'USER', 1)"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO courses (id, title, slug, short_description, description, category, tags, price, currency, difficulty, instructor, duration_minutes, is_active) "
                "VALUES ('c1', 'Title', 'slug-1', 'short', 'desc', 'cat', '[]', 0, 'USD', 'BEGINNER', 'inst', 60, 1)"
            )
        )
    await engine.dispose()

    # Upgrade to head
    await asyncio.to_thread(command.upgrade, config, "head")

    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        user_count = await conn.scalar(text("SELECT COUNT(*) FROM users"))
        course_count = await conn.scalar(text("SELECT COUNT(*) FROM courses"))
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
    await engine.dispose()

    assert user_count == 1
    assert course_count == 1
    assert "enrollments" in tables


@pytest.mark.asyncio
async def test_migration_downgrade_and_reupgrade(tmp_path, monkeypatch):
    db_path = tmp_path / "downgrade_test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    monkeypatch.setattr(settings, "database_url", db_url)

    config = get_alembic_config(db_url)

    # Upgrade to head
    await asyncio.to_thread(command.upgrade, config, "head")

    # Insert data into users and enrollments
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, full_name, email, password_hash, role, is_active) "
                "VALUES ('u1', 'Test User', 'user@test.com', 'hash', 'USER', 1)"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO courses (id, title, slug, short_description, description, category, tags, price, currency, difficulty, instructor, duration_minutes, is_active) "
                "VALUES ('c1', 'Title', 'slug-1', 'short', 'desc', 'cat', '[]', 0, 'USD', 'BEGINNER', 'inst', 60, 1)"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO enrollments (id, user_id, course_id, status, started_at, last_accessed_at) "
                "VALUES ('e1', 'u1', 'c1', 'ACTIVE', '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
        )
    await engine.dispose()

    # Downgrade to 0003
    await asyncio.to_thread(command.downgrade, config, "0003_recommendations")

    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        user_count = await conn.scalar(text("SELECT COUNT(*) FROM users"))
    await engine.dispose()

    assert "enrollments" not in tables
    assert user_count == 1

    # Re-upgrade to head
    await asyncio.to_thread(command.upgrade, config, "head")

    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        rev = await conn.scalar(text("SELECT version_num FROM alembic_version"))
    await engine.dispose()

    assert "enrollments" in tables
    assert rev == "0007_recommendation_feedback"
