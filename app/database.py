import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)


def _build_engine_kwargs() -> dict:
    base: dict = {
        "echo": settings.ENVIRONMENT == "development",
        "pool_pre_ping": True,
    }

    if settings.is_sqlite:
        base["connect_args"] = {"check_same_thread": False}
    else:
        base["pool_size"]    = settings.DB_POOL_SIZE
        base["max_overflow"] = settings.DB_MAX_OVERFLOW
        base["pool_timeout"] = settings.DB_POOL_TIMEOUT
        base["pool_recycle"] = settings.DB_POOL_RECYCLE
        base["connect_args"] = {
            "server_settings": {"application_name": "dftlabs_api"}
        }

    return base


engine = create_async_engine(settings.DATABASE_URL, **_build_engine_kwargs())

AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def create_db_and_tables() -> None:
    """Create all SQLModel tables. Called once at startup."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    logger.info("Database tables ready")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yields one AsyncSession per request. Commits on success, rolls back on exception."""
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_session_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Use in agents and background tasks that run outside FastAPI request context.

    Example:
        async with get_session_context() as db:
            db.add(some_model)
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()