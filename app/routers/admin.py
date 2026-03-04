import logging

from fastapi import APIRouter, HTTPException, status
from sqlmodel import SQLModel

from app.auth.jwt import AdminDep, create_access_token
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["Admin"])


class LoginRequest(SQLModel):
    password: str


class TokenResponse(SQLModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest) -> TokenResponse:
    if body.password != settings.ADMIN_PASSWORD:
        logger.warning("Failed admin login attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
        )
    logger.info("Admin login successful")
    return TokenResponse(
        access_token=create_access_token(
            {"role": "admin", "sub": "dft_admin"}
        )
    )


@router.post("/run-research-agent", summary="Trigger research agent manually")
async def trigger_research(_: AdminDep) -> dict:
    from app.agents.research_agent import run_research_agent
    logger.info("Research agent manually triggered by admin")
    count = await run_research_agent()
    return {"drafts_created": count}


@router.post("/run-jobs-agent", summary="Trigger jobs agent manually")
async def trigger_jobs(_: AdminDep) -> dict:
    from app.agents.jobs_agent import run_jobs_agent
    logger.info("Jobs agent manually triggered by admin")
    count = await run_jobs_agent()
    return {"new_jobs": count}