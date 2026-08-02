import re
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import database as app_db
from app.config import settings
from app.database import get_db
from app.main import app
from app.models import Base, Course, User
from app.security import hash_password
import app.services.vector_sync_service as sync_service
import scripts.create_admin as create_admin_script
import scripts.reconcile_vectors as reconcile_script
import scripts.seed_data as seed_script


@pytest.fixture(autouse=True)
def isolate_qdrant(tmp_path, monkeypatch):
    unique_id = uuid.uuid4().hex[:8]
    test_qdrant_dir = str(tmp_path / f"qdrant_test_{unique_id}")
    test_collection_name = f"smartreco_courses_test_{unique_id}"

    monkeypatch.setattr(settings, "qdrant_path", test_qdrant_dir)
    monkeypatch.setattr(settings, "qdrant_collection", test_collection_name)

    yield test_qdrant_dir, test_collection_name


@pytest_asyncio.fixture
async def db_session(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(app_db, "async_session_maker", maker)
    monkeypatch.setattr(sync_service, "async_session_maker", maker)
    monkeypatch.setattr(seed_script, "async_session_maker", maker)
    monkeypatch.setattr(create_admin_script, "async_session_maker", maker)
    monkeypatch.setattr(reconcile_script, "async_session_maker", maker)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session):
    async def override():
        yield db_session
    app.dependency_overrides[get_db] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as http:
        yield http
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_user(db_session):
    user = User(full_name="System Admin", email="admin@smartreco.org", password_hash=hash_password("AdminPass123!"), role="ADMIN")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def regular_user(db_session):
    user = User(full_name="Regular Student", email="student@example.com", password_hash=hash_password("StudentPass123!"), role="USER")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def course(db_session):
    item = Course(title="Python Foundations", slug="python-foundations", short_description="A practical Python starting point.", description="Learn the language through small, useful programs and clear explanations.", category="Python", tags=["python", "practice"], price=0, currency="USD", difficulty="BEGINNER", instructor="Asha Menon", duration_minutes=90, is_featured=True, is_active=True, version=1, vector_status="PENDING")
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


def csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)', html) or re.search(r'<meta name="csrf-token" content="([^"]+)', html)
    return match.group(1)
