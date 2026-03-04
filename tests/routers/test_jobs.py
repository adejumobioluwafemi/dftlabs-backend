# tests/routers/test_jobs.py
import pytest
from httpx import AsyncClient

VALID_JOB = {
    "role": "ML Engineer",
    "company": "HealthTech Africa",
    "location": "Remote",
    "job_type": "Full-time",
    "sector": "Healthcare",
    "salary": "$80k–$100k",
    "apply_url": "https://example.com/apply",
    "source": "test",
    "source_id": "test-001",
}

SECOND_JOB = {
    "role": "Data Scientist",
    "company": "AgriMind",
    "location": "Lagos, NG",
    "job_type": "Contract",
    "sector": "Agriculture",
    "source": "test",
    "source_id": "test-002",
}


async def _create_job(client: AsyncClient, headers: dict, data: dict) -> dict:
    """Helper — insert a job directly via the agent save path."""
    from app.models.job import Job
    # Use the session via a direct DB insert through the agent helper
    # For router tests we seed via the jobs agent's internal save
    # Instead, expose a test-only admin create endpoint shim:
    resp = await client.post("/api/jobs/admin/", json=data, headers=headers)
    return resp.json()


@pytest.mark.asyncio
async def test_list_jobs_empty(client: AsyncClient) -> None:
    resp = await client.get("/api/jobs/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_and_list_job(
    client: AsyncClient, auth_headers: dict, db_session
) -> None:
    from app.models.job import Job
    from sqlmodel.ext.asyncio.session import AsyncSession

    # Seed directly via DB session (jobs have no public create endpoint)
    job = Job(**VALID_JOB) # type: ignore
    db_session.add(job)
    await db_session.flush() 
    await db_session.refresh(job)

    resp = await client.get("/api/jobs/")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["role"] == "ML Engineer"


@pytest.mark.asyncio
async def test_filter_by_sector(
    client: AsyncClient, auth_headers: dict, db_session
) -> None:
    from app.models.job import Job

    db_session.add(Job(**VALID_JOB)) # type: ignore
    db_session.add(Job(**SECOND_JOB)) # type: ignore
    await db_session.commit()

    resp = await client.get("/api/jobs/?sector=Healthcare")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["sector"] == "Healthcare"

    resp = await client.get("/api/jobs/?sector=Agriculture")
    assert len(resp.json()) == 1
    assert resp.json()[0]["sector"] == "Agriculture"


@pytest.mark.asyncio
async def test_search_jobs(
    client: AsyncClient, db_session
) -> None:
    from app.models.job import Job

    db_session.add(Job(**VALID_JOB)) # type: ignore
    db_session.add(Job(**SECOND_JOB)) # type: ignore
    await db_session.commit()

    resp = await client.get("/api/jobs/?search=HealthTech")
    assert len(resp.json()) == 1
    assert resp.json()[0]["company"] == "HealthTech Africa"


@pytest.mark.asyncio
async def test_hidden_job_not_listed(
    client: AsyncClient, auth_headers: dict, db_session
) -> None:
    from app.models.job import Job
    from app.services.cache_service import cache  # import your cache
    job = Job(**{**VALID_JOB, "is_visible": False})
    db_session.add(job)
    await db_session.commit()
    cache.clear()  # flush stale cache from prior tests
    resp = await client.get("/api/jobs/")
    assert resp.json() == []


@pytest.mark.asyncio
async def test_toggle_job_visibility(
    client: AsyncClient, auth_headers: dict, db_session
) -> None:
    from app.models.job import Job

    job = Job(**VALID_JOB) # type: ignore
    db_session.add(job)
    await db_session.flush() 
    await db_session.refresh(job)

    # Hide it
    resp = await client.patch(
        f"/api/jobs/admin/{job.id}",
        json={"is_visible": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_visible"] is False

    # Confirm not in public listing
    resp = await client.get("/api/jobs/")
    assert resp.json() == []


@pytest.mark.asyncio
async def test_feature_job(
    client: AsyncClient, auth_headers: dict, db_session
) -> None:
    from app.models.job import Job

    job = Job(**VALID_JOB) # type: ignore
    db_session.add(job)
    await db_session.flush() 
    await db_session.refresh(job)

    resp = await client.patch(
        f"/api/jobs/admin/{job.id}",
        json={"is_featured": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_featured"] is True


@pytest.mark.asyncio
async def test_delete_job(
    client: AsyncClient, auth_headers: dict, db_session
) -> None:
    from app.models.job import Job

    job = Job(**VALID_JOB) # type: ignore
    db_session.add(job)
    await db_session.flush() 
    await db_session.refresh(job)

    resp = await client.delete(
        f"/api/jobs/admin/{job.id}", headers=auth_headers
    )
    assert resp.status_code == 204

    resp = await client.get("/api/jobs/")
    assert resp.json() == []


@pytest.mark.asyncio
async def test_update_nonexistent_job(
    client: AsyncClient, auth_headers: dict
) -> None:
    resp = await client.patch(
        "/api/jobs/admin/99999",
        json={"is_visible": False},
        headers=auth_headers,
    )
    assert resp.status_code == 404