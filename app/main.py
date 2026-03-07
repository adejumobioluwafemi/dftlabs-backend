# app/main.py
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.config import settings
from app.core.logging import setup_logging
from app.core.scheduler import shutdown_scheduler, start_scheduler
from app.database import create_db_and_tables
from app.routers import admin, blog, events, jobs, registrations, products

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("DFT Labs API starting — env=%s", settings.ENVIRONMENT)
    await create_db_and_tables()
    if not settings.is_testing:
        start_scheduler()
    logger.info("DFT Labs API ready ✅")
    yield
    shutdown_scheduler()
    logger.info("DFT Labs API shut down")


app = FastAPI(
    title="DeepFly Tech Labs API",
    description="Production API for deepflytechlabs.com",
    version="1.0.0",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
for _router in [
    admin.router,
    blog.router,
    jobs.router,
    events.router,
    registrations.router,
    products.router,
]:
    app.include_router(_router)

# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["Meta"])
async def health() -> dict:
    return {
        "status": "ok",
        "version": "1.0.0",
        "env": settings.ENVIRONMENT,
    }