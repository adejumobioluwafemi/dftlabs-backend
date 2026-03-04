import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.jwt import AdminDep
from app.database import get_session
from app.models.job import Job, JobPublic, JobUpdate
from app.services.cache_service import cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/jobs", tags=["Jobs"])
DBSession = Annotated[AsyncSession, Depends(get_session)]


@router.get("/", response_model=list[JobPublic])
async def list_jobs(
    db: DBSession,
    sector: str | None = Query(None),
    job_type: str | None = Query(None),
    location: str | None = Query(None),
    search: str | None = Query(None, max_length=100),
    featured: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[Job]:
    cache_key = f"jobs:{sector}:{job_type}:{location}:{search}:{featured}:{limit}:{offset}"
    if cached := cache.get(cache_key):
        return cached

    stmt = (
        select(Job)
        .where(Job.is_visible == True)  # noqa: E712
        .order_by(Job.is_featured.desc(), Job.created_at.desc()) # type: ignore
        .limit(limit)
        .offset(offset)
    )
    if sector:
        stmt = stmt.where(Job.sector == sector)
    if job_type:
        stmt = stmt.where(Job.job_type == job_type)
    if location and location != "All":
        stmt = stmt.where(Job.location == location)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(Job.role.ilike(like) | Job.company.ilike(like)) # type: ignore
    if featured:
        stmt = stmt.where(Job.is_featured == True)  # noqa: E712

    result = (await db.exec(stmt)).all()
    cache.set(cache_key, result, ttl=180)
    logger.debug("Listed %d jobs", len(result))
    return result # type: ignore


@router.patch("/admin/{job_id}", response_model=JobPublic)
async def update_job(
    job_id: int,
    updates: JobUpdate,
    db: DBSession,
    _: AdminDep,
) -> Job:
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    for field_name, value in updates.model_dump(exclude_unset=True).items():
        setattr(job, field_name, value)
    db.add(job)
    await db.flush()
    await db.refresh(job)
    cache.invalidate("jobs:")
    logger.info("Admin: updated job id=%d", job_id)
    return job


@router.delete("/admin/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: int, db: DBSession, _: AdminDep) -> None:
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    await db.delete(job)
    cache.invalidate("jobs:")
    logger.info("Admin: deleted job id=%d", job_id)