# tests/agents/test_jobs_agent.py
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
import pytest
from sqlmodel import select

from app.agents.jobs_agent import (
    AgentState,
    RawJob,
    _action_fetch_arbeitnow,
    _action_fetch_remoteok,
    _classify_sector,
    _is_ai_job,
    run_jobs_agent,
)
from app.models.job import Job
from tests.routers.test_jobs import VALID_JOB


# ── Unit tests ────────────────────────────────────────────────────────────────

def test_is_ai_job_true() -> None:
    assert _is_ai_job("Senior Machine Learning Engineer at HealthTech")
    assert _is_ai_job("Data Scientist — NLP focus")
    assert _is_ai_job("MLOps Engineer — model deployment")


def test_is_ai_job_false() -> None:
    assert not _is_ai_job("Senior Accountant at Finance Corp")
    assert not _is_ai_job("Marketing Manager — social media")


def test_classify_sector_healthcare() -> None:
    assert _classify_sector("medical AI clinical health patient") == "Healthcare"


def test_classify_sector_banking() -> None:
    assert _classify_sector("fraud detection fintech banking risk") == "Banking"


def test_classify_sector_general() -> None:
    assert _classify_sector("senior software engineer golang") == "General AI"


# ── Integration tests with mocked HTTP ───────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_remoteok_handles_error() -> None:
    """Fetch gracefully handles HTTP errors."""
    with patch("httpx.AsyncClient.get", side_effect=Exception("timeout")):
        state = AgentState()
        await _action_fetch_remoteok(state)
        assert state.jobs_raw == []
        assert len(state.errors) == 1


@pytest.mark.asyncio
async def test_run_jobs_agent_saves_new_jobs(db_session) -> None:
    """Agent saves new jobs and skips duplicates."""
    mock_jobs = [
        RawJob(
            role="ML Engineer",
            company="HealthAI",
            location="Remote",
            job_type="Full-time",
            apply_url="https://example.com/1",
            source="remoteok",
            source_id="remoteok-001",
            sector="Healthcare",
        ),
        RawJob(
            role="Data Scientist",
            company="AgriTech",
            location="Lagos",
            job_type="Full-time",
            apply_url="https://example.com/2",
            source="remoteok",
            source_id="remoteok-002",
            sector="Agriculture",
        ),
    ]

    with (
        patch(
            "app.agents.jobs_agent._action_fetch_remoteok",
            new_callable=AsyncMock,
        ) as mock_remote,
        patch(
            "app.agents.jobs_agent._action_fetch_arbeitnow",
            new_callable=AsyncMock,
        ) as mock_arb,
        patch(
            "app.agents.jobs_agent.get_session_context"
        ) as mock_ctx,
    ):
        # Populate state in the mock
        async def fake_remoteok(state: AgentState) -> None:
            state.jobs_raw.extend(mock_jobs)

        mock_remote.side_effect = fake_remoteok
        mock_arb.side_effect = lambda state: None

        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await run_jobs_agent()
        assert result == 2


@pytest.mark.asyncio
async def test_run_jobs_agent_deduplicates(db_session) -> None:
    """Agent skips jobs that already exist in DB."""
    # Pre-seed an existing job
    existing = Job(
        role="ML Engineer",
        company="HealthAI",
        location="Remote",
        job_type="Full-time",
        sector="Healthcare",
        source="remoteok",
        source_id="remoteok-001",
    )
    db_session.add(existing)
    await db_session.commit()

    mock_job = RawJob(
        role="ML Engineer",
        company="HealthAI",
        location="Remote",
        job_type="Full-time",
        apply_url="https://example.com/1",
        source="remoteok",
        source_id="remoteok-001",  # same source_id
        sector="Healthcare",
    )

    with (
        patch(
            "app.agents.jobs_agent._action_fetch_remoteok",
            new_callable=AsyncMock,
        ) as mock_remote,
        patch(
            "app.agents.jobs_agent._action_fetch_arbeitnow",
            new_callable=AsyncMock,
        ) as mock_arb,
        patch(
            "app.agents.jobs_agent.get_session_context"
        ) as mock_ctx,
    ):
        async def fake_remoteok(state: AgentState) -> None:
            state.jobs_raw.append(mock_job)

        mock_remote.side_effect = fake_remoteok
        mock_arb.side_effect = lambda state: None

        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await run_jobs_agent()
        assert result == 0  # nothing new saved
