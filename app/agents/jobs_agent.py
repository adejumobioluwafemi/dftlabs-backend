"""
app/agents/jobs_agent.py
Jobs Aggregator Agent — ReAct Architecture
==========================================

ReAct loop:  Thought → Action → Observation → Thought → ...

Nodes:
  1. FETCH_REMOTEOK   — fetch AI jobs from RemoteOK public API
  2. FETCH_ARBEITNOW  — fetch jobs from Arbeitnow public API
  3. THINK            — deduplicate and classify sector
  4. SAVE             — persist new jobs to DB (is_visible=True)

Admin can hide or feature jobs from the admin panel.
New jobs auto-appear on the public jobs board.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC

import httpx
from sqlmodel import select

from app.database import get_session_context
from app.models.job import Job

logger = logging.getLogger(__name__)


# ── Domain types ──────────────────────────────────────────────────────────────

@dataclass
class RawJob:
    role: str
    company: str
    location: str
    job_type: str
    apply_url: str | None
    source: str
    source_id: str
    salary: str | None = None
    description: str | None = None
    sector: str = "General AI"


@dataclass
class AgentState:
    jobs_raw: list[RawJob] = field(default_factory=list)
    jobs_new: int = 0
    jobs_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    thoughts: list[str] = field(default_factory=list)


# ── Sector + relevance classification ────────────────────────────────────────

SECTOR_KEYWORDS: dict[str, list[str]] = {
    "Healthcare": [
        "health", "medical", "clinical", "hospital",
        "pharma", "patient", "biotech",
    ],
    "Agriculture": [
        "agri", "farm", "crop", "food", "precision",
        "irrigation", "soil",
    ],
    "Banking": [
        "bank", "finance", "fintech", "payment",
        "insurance", "fraud", "risk", "trading",
    ],
    "Education": [
        "education", "edtech", "learning", "school",
        "curriculum", "teach", "university",
    ],
}

AI_KEYWORDS = [
    "machine learning", "ml engineer", "data scientist",
    "artificial intelligence", " ai ", "nlp", "computer vision",
    "deep learning", "llm", "mlops", "data engineer",
    "ml ops", "generative ai", "ai red-teamer"
]


def _is_ai_job(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in AI_KEYWORDS)


def _classify_sector(text: str) -> str:
    t = text.lower()
    scores = {
        s: sum(1 for kw in kws if kw in t)
        for s, kws in SECTOR_KEYWORDS.items()
    }
    best = max(scores, key=scores.get) # type: ignore
    return best if scores[best] > 0 else "General AI"


# ── Actions ───────────────────────────────────────────────────────────────────

async def _action_fetch_remoteok(state: AgentState) -> None:
    """ACTION: Fetch AI jobs from RemoteOK (free public API)."""
    thought = "Fetching AI jobs from RemoteOK public API"
    state.thoughts.append(thought)
    logger.info("[Jobs Agent] %s", thought)

    async with httpx.AsyncClient(
        timeout=20,
        headers={"User-Agent": "DFTLabs-JobsAgent/1.0 (deepflytechlabs.com)"},
    ) as http:
        try:
            resp = await http.get("https://remoteok.com/api?tag=ai")
            resp.raise_for_status()
            raw = resp.json()

            jobs: list[RawJob] = []
            for item in raw[1:]:  # index 0 is metadata
                if not isinstance(item, dict):
                    continue

                text = (
                    f"{item.get('position', '')} "
                    f"{item.get('company', '')} "
                    f"{' '.join(item.get('tags', []))}"
                )
                if not _is_ai_job(text):
                    continue

                salary = None
                if item.get("salary_min"):
                    lo = item["salary_min"]
                    hi = item.get("salary_max", lo)
                    salary = f"${lo:,}–${hi:,}"

                jobs.append(
                    RawJob(
                        role=item.get("position", "")[:300],
                        company=item.get("company", "")[:200],
                        location="Remote",
                        job_type="Full-time",
                        apply_url=item.get("url"),
                        source="remoteok",
                        source_id=str(item.get("id", "")),
                        salary=salary,
                        sector=_classify_sector(text),
                    )
                )

            state.jobs_raw.extend(jobs[:20])
            obs = f"Fetched {len(jobs)} AI jobs from RemoteOK"
            state.thoughts.append(f"Observation: {obs}")
            logger.info("[Jobs Agent] %s", obs)

        except Exception as exc:
            msg = f"RemoteOK fetch failed: {exc}"
            state.errors.append(msg)
            logger.warning("[Jobs Agent] %s", msg)


async def _action_fetch_arbeitnow(state: AgentState) -> None:
    """ACTION: Fetch jobs from Arbeitnow (free API, no key needed)."""
    thought = "Fetching AI jobs from Arbeitnow API"
    state.thoughts.append(thought)
    logger.info("[Jobs Agent] %s", thought)

    async with httpx.AsyncClient(timeout=20) as http:
        try:
            resp = await http.get(
                "https://www.arbeitnow.com/api/job-board-api?page=1"
            )
            resp.raise_for_status()

            jobs: list[RawJob] = []
            for item in resp.json().get("data", []):
                text = (
                    f"{item.get('title', '')} "
                    f"{item.get('company_name', '')} "
                    f"{item.get('description', '')[:300]}"
                )
                if not _is_ai_job(text):
                    continue

                jobs.append(
                    RawJob(
                        role=item.get("title", "")[:300],
                        company=item.get("company_name", "")[:200],
                        location=item.get("location", "Remote")[:200],
                        job_type="Full-time",
                        apply_url=item.get("url"),
                        source="arbeitnow",
                        source_id=item.get("slug", ""),
                        sector=_classify_sector(text),
                    )
                )

            state.jobs_raw.extend(jobs[:15])
            obs = f"Fetched {len(jobs)} AI jobs from Arbeitnow"
            state.thoughts.append(f"Observation: {obs}")
            logger.info("[Jobs Agent] %s", obs)

        except Exception as exc:
            msg = f"Arbeitnow fetch failed: {exc}"
            state.errors.append(msg)
            logger.warning("[Jobs Agent] %s", msg)


async def _action_save_new_jobs(state: AgentState) -> None:
    """
    ACTION: Deduplicate against DB and save new jobs.
    Thought: Only save jobs we haven't seen before (source_id dedup).
    """
    thought = (
        f"Deduplicating {len(state.jobs_raw)} raw jobs "
        f"against existing DB records"
    )
    state.thoughts.append(thought)
    logger.info("[Jobs Agent] %s", thought)

    async with get_session_context() as db:
        for raw in state.jobs_raw:
            if not raw.source_id:
                state.jobs_skipped += 1
                continue

            # Dedup check
            existing = (
                await db.exec(
                    select(Job).where(Job.source_id == raw.source_id)
                )
            ).first()

            if existing:
                state.jobs_skipped += 1
                continue

            db.add(
                Job(
                    role=raw.role,
                    company=raw.company,
                    location=raw.location,
                    job_type=raw.job_type,
                    sector=raw.sector,
                    salary=raw.salary,
                    apply_url=raw.apply_url,
                    source=raw.source,
                    source_id=raw.source_id,
                    is_visible=True,
                )
            )
            state.jobs_new += 1

        await db.flush()

    obs = (
        f"Saved {state.jobs_new} new jobs, "
        f"skipped {state.jobs_skipped} duplicates"
    )
    state.thoughts.append(f"Observation: {obs}")
    logger.info("[Jobs Agent] %s", obs)


# ── Main ReAct loop ───────────────────────────────────────────────────────────

async def run_jobs_agent() -> int:
    """
    Main entry point for the Jobs Aggregator Agent.

    ReAct loop:
        FETCH_REMOTEOK → FETCH_ARBEITNOW → THINK (dedup) → SAVE → DONE
    """
    logger.info("[Jobs Agent] Starting ReAct loop")
    state = AgentState()

    state.thoughts.append(
        "Thought: I need to fetch AI job listings from public APIs, "
        "filter for AI relevance, deduplicate, and save new ones."
    )

    # ── Fetch ─────────────────────────────────────────────────────────────────
    await _action_fetch_remoteok(state)
    await _action_fetch_arbeitnow(state)

    # ── Think + Save ──────────────────────────────────────────────────────────
    if not state.jobs_raw:
        logger.warning("[Jobs Agent] No jobs fetched from any source")
        return 0

    state.thoughts.append(
        f"Thought: Have {len(state.jobs_raw)} raw jobs. "
        f"Will deduplicate and save only unseen ones."
    )
    await _action_save_new_jobs(state)

    # ── Done ──────────────────────────────────────────────────────────────────
    logger.info(
        "[Jobs Agent] Done — %d new, %d skipped, %d errors. "
        "Thought steps: %d",
        state.jobs_new,
        state.jobs_skipped,
        len(state.errors),
        len(state.thoughts),
    )
    return state.jobs_new