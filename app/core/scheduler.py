import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings

logger = logging.getLogger(__name__)
_scheduler = AsyncIOScheduler(timezone="Africa/Lagos")


def start_scheduler() -> None:
    from app.agents.jobs_agent import run_jobs_agent
    from app.agents.research_agent import run_research_agent

    _scheduler.add_job(
        run_research_agent,
        CronTrigger.from_crontab(settings.RESEARCH_AGENT_CRON),
        id="research_agent",
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )
    _scheduler.add_job(
        run_jobs_agent,
        CronTrigger.from_crontab(settings.JOBS_AGENT_CRON),
        id="jobs_agent",
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )
    _scheduler.start()
    logger.info(
        "Scheduler started — research: '%s' | jobs: '%s' (timezone: Africa/Lagos)",
        settings.RESEARCH_AGENT_CRON,
        settings.JOBS_AGENT_CRON,
    )


def shutdown_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")