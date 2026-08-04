import logging
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

REQUIRED_TABLES = {
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
}


async def check_schema_readiness(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        tables = set(await connection.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names()))
        missing = REQUIRED_TABLES - tables
        if missing:
            missing_str = ", ".join(sorted(missing))
            msg = f"Database schema is not ready: required table(s) '{missing_str}' missing. Run: ./.venv311/bin/python -m alembic upgrade head"
            logger.error(msg)
            raise RuntimeError(msg)

        if "alembic_version" not in tables:
            msg = "Database schema is not ready: 'alembic_version' table is missing. Run: ./.venv311/bin/python -m alembic upgrade head"
            logger.error(msg)
            raise RuntimeError(msg)

        rows = (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
        if not rows:
            msg = "Database schema is not ready: 'alembic_version' table is empty. Run: ./.venv311/bin/python -m alembic upgrade head"
            logger.error(msg)
            raise RuntimeError(msg)
