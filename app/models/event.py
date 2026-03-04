from datetime import datetime, UTC
from typing import Optional

from pydantic import field_validator
from sqlmodel import Field, SQLModel


class EventBase(SQLModel):
    title: str = Field(min_length=1, max_length=500)
    event_type: str = Field(max_length=100)
    date: str = Field(max_length=100)
    time: str = Field(max_length=100)
    location: str = Field(max_length=300)
    price: str = Field(default="Free", max_length=100)
    short_desc: str = Field(min_length=1)
    description: str = Field(min_length=1)
    speakers: Optional[str] = Field(default=None)
    image: Optional[str] = Field(default=None, max_length=500)
    max_spots: int = Field(default=50)

    @field_validator("max_spots")
    @classmethod
    def max_spots_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("max_spots must be greater than 0")
        return v


class Event(EventBase, table=True):
    __tablename__ = "events" # type: ignore

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(max_length=200, unique=True, index=True)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class EventCreate(EventBase):
    slug: str = Field(max_length=200)


class EventUpdate(SQLModel):
    title: Optional[str] = Field(default=None, max_length=500)
    date: Optional[str] = Field(default=None, max_length=100)
    time: Optional[str] = Field(default=None, max_length=100)
    location: Optional[str] = Field(default=None, max_length=300)
    price: Optional[str] = Field(default=None, max_length=100)
    short_desc: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    speakers: Optional[str] = Field(default=None)
    image: Optional[str] = Field(default=None, max_length=500)
    max_spots: Optional[int] = Field(default=None)
    is_active: Optional[bool] = Field(default=None)

    @field_validator("max_spots")
    @classmethod
    def max_spots_positive(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v <= 0:
            raise ValueError("max_spots must be greater than 0")
        return v


class EventPublic(EventBase):
    id: int
    slug: str
    is_active: bool
    filled: int = 0
    created_at: datetime