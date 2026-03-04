import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.jwt import AdminDep
from app.database import get_session
from app.models.event import Event
from app.models.registration import Registration, RegistrationCreate, RegistrationPublic
from app.services.cache_service import cache
from app.services.email_service import send_confirmation_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/registrations", tags=["Registrations"])
DBSession = Annotated[AsyncSession, Depends(get_session)]


@router.post(
    "/",
    response_model=RegistrationPublic,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    body: RegistrationCreate,
    background: BackgroundTasks,
    db: DBSession,
) -> Registration:
    # 1. Verify event exists and is active
    event = await db.get(Event, body.event_id)
    if not event or not event.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    # 2. Check capacity
    filled = (
        await db.exec(
            select(func.count()).where(
                Registration.event_id == body.event_id
            )
        )
    ).one()
    if filled >= event.max_spots:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Event is fully booked",
        )

    # 3. Prevent duplicate registration
    existing = (
        await db.exec(
            select(Registration).where(
                Registration.event_id == body.event_id,
                Registration.email == body.email,
            )
        )
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email is already registered for this event",
        )

    # 4. Persist registration
    reg = Registration.model_validate(body)
    db.add(reg)
    await db.flush()
    await db.refresh(reg)

    # Invalidate event cache so filled count updates
    cache.invalidate("events:")

    # 5. Send confirmation email (non-blocking background task)
    background.add_task(
        send_confirmation_email,
        to_email=str(body.email),
        name=f"{body.first_name} {body.last_name}",
        event_title=event.title,
        event_date=event.date,
        event_time=event.time,
        event_location=event.location,
        is_virtual=body.is_virtual,
    )

    logger.info(
        "New registration: %s for event_id=%d", body.email, body.event_id
    )
    return reg


@router.get(
    "/admin/event/{event_id}",
    response_model=list[RegistrationPublic],
)
async def get_registrations(
    event_id: int,
    db: DBSession,
    _: AdminDep,
) -> list[Registration]:
    result = (
        await db.exec(
            select(Registration)
            .where(Registration.event_id == event_id)
            .order_by(Registration.registered_at.desc()) # type: ignore
        )
    ).all()
    logger.debug(
        "Admin: fetched %d registrations for event_id=%d",
        len(result),
        event_id,
    )
    return result # type: ignore