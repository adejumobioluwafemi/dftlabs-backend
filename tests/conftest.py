import os
import pytest
import pytest_asyncio
from collections.abc import AsyncGenerator
from unittest.mock import patch

# ── Force test environment BEFORE any app imports ────────────────────────────
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-exactly-64-chars-long-for-jwt-signing-in-tests!"
os.environ["ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"
os.environ["ADMIN_PASSWORD"] = "test-admin-password"
os.environ["ANTHROPIC_API_KEY"] = "test-key-not-real"
os.environ["RESEND_API_KEY"] = ""
os.environ["FROM_EMAIL"] = "test@example.com"
os.environ["FRONTEND_URL"] = "http://localhost:5173"
os.environ["DB_POOL_SIZE"] = "1"
os.environ["DB_MAX_OVERFLOW"] = "0"
os.environ["DB_POOL_TIMEOUT"] = "10"
os.environ["DB_POOL_RECYCLE"] = "3600"
os.environ["RESEARCH_AGENT_CRON"] = "0 8 * * 1"
os.environ["JOBS_AGENT_CRON"] = "0 6 * * *"

# Clear lru_cache so Settings re-reads from os.environ above
from app.config import get_settings
get_settings.cache_clear()

# NOW safe to import app modules
from httpx import ASGITransport, AsyncClient
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.main import app
from app.database import get_session
from app.config import settings

# Verify test settings loaded correctly
assert settings.ENVIRONMENT == "test", f"Expected test, got {settings.ENVIRONMENT}"
assert settings.ADMIN_PASSWORD == "test-admin-password", "Wrong admin password in test"

# ── In-memory SQLite engine for tests ────────────────────────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

TestSessionFactory = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_db():
    """Create all tables before each test, drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionFactory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTP test client with DB session injected."""

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient) -> str:
    """Get a valid admin JWT token."""
    resp = await client.post(
        "/api/admin/login",
        json={"password": "test-admin-password"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.json()}"
    return resp.json()["access_token"]


@pytest_asyncio.fixture # type: ignore
def auth_headers(admin_token: str) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}