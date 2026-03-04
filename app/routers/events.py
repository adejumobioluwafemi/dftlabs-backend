import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.jwt import AdminDep
from app.database import get_session
from app.models.event import Event, EventCreate, EventPublic, EventUpdate
from app.models.registration import Registration
from app.services.cache_service import cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/events", tags=["Events"])
DBSession = Annotated[AsyncSession, Depends(get_session)]


async def _attach_filled(event: Event, db: AsyncSession) -> EventPublic:
    count = (
        await db.exec(
            select(func.count()).where(Registration.event_id == event.id)
        )
    ).one()
    public = EventPublic.model_validate(event)
    public.filled = count
    return public


@router.get("/", response_model=list[EventPublic])
async def list_events(db: DBSession) -> list[EventPublic]:
    if cached := cache.get("events:active"):
        return cached

    events = (
        await db.exec(
            select(Event)
            .where(Event.is_active == True)  # noqa: E712
            .order_by(Event.date)
        )
    ).all()
    result = [await _attach_filled(e, db) for e in events]
    cache.set("events:active", result, ttl=120)
    return result


@router.get("/{slug}", response_model=EventPublic)
async def get_event(slug: str, db: DBSession) -> EventPublic:
    cache_key = f"events:{slug}"
    if cached := cache.get(cache_key):
        return cached

    event = (
        await db.exec(select(Event).where(Event.slug == slug))
    ).first()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )
    result = await _attach_filled(event, db)
    cache.set(cache_key, result, ttl=120)
    return result


@router.post(
    "/admin/",
    response_model=EventPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_event(
    event: EventCreate, db: DBSession, _: AdminDep
) -> EventPublic:
    db_event = Event.model_validate(event)
    db.add(db_event)
    await db.flush()
    await db.refresh(db_event)
    cache.invalidate("events:")
    logger.info("Admin: created event slug=%s", db_event.slug)
    return await _attach_filled(db_event, db)


@router.patch("/admin/{event_id}", response_model=EventPublic)
async def update_event(
    event_id: int,
    updates: EventUpdate,
    db: DBSession,
    _: AdminDep,
) -> EventPublic:
    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )
    for field_name, value in updates.model_dump(exclude_unset=True).items():
        setattr(event, field_name, value)
    db.add(event)
    await db.flush()
    await db.refresh(event)
    cache.invalidate("events:")
    logger.info("Admin: updated event id=%d", event_id)
    return await _attach_filled(event, db)


@router.delete("/admin/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(event_id: int, db: DBSession, _: AdminDep) -> None:
    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )
    await db.delete(event)
    cache.invalidate("events:")
    logger.info("Admin: deleted event id=%d", event_id)