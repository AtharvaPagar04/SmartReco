import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.services.schema_readiness_service import check_schema_readiness


@pytest.mark.asyncio
async def test_schema_readiness_fails_on_missing_table(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'incomplete.db'}"
    engine = create_async_engine(db_url)

    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
        await conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        await conn.execute(text("INSERT INTO alembic_version VALUES ('0003_recommendations')"))

    with pytest.raises(RuntimeError) as exc_info:
        await check_schema_readiness(engine)

    assert "Database schema is not ready: required table(s)" in str(exc_info.value)
    assert "enrollments" in str(exc_info.value)
    assert "alembic upgrade head" in str(exc_info.value)

    await engine.dispose()


@pytest.mark.asyncio
async def test_schema_readiness_passes_when_all_tables_exist(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'complete.db'}"
    engine = create_async_engine(db_url)

    required_tables = [
        "users",
        "courses",
        "activity_events",
        "vector_outbox",
        "enrollments",
        "user_interest_profiles",
        "recommendation_states",
        "recommendation_runs",
        "recommendation_items",
        "recommendation_preferences",
        "recommendation_deliveries",
        "shopping_carts",
        "cart_items",
        "orders",
        "order_items",
        "course_entitlements",
    ]

    async with engine.begin() as conn:
        for table in required_tables:
            await conn.execute(text(f"CREATE TABLE {table} (id VARCHAR(36) PRIMARY KEY)"))
        await conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        await conn.execute(text("INSERT INTO alembic_version VALUES ('0004_enrollments')"))

    # Should not raise
    await check_schema_readiness(engine)
    await engine.dispose()
