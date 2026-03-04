from datetime import datetime, UTC
from typing import Optional

from pydantic import EmailStr
from sqlmodel import Field, SQLModel


class RegistrationBase(SQLModel):
    first_name: str = Field(min_length=1, max_length=200)
    last_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=100)
    organization: Optional[str] = Field(default=None, max_length=300)
    role: Optional[str] = Field(default=None, max_length=200)
    is_virtual: bool = Field(default=False)


class Registration(RegistrationBase, table=True):
    __tablename__ = "registrations" # type: ignore

    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: int = Field(foreign_key="events.id", index=True)
    confirmed: bool = Field(default=True)
    registered_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class RegistrationCreate(RegistrationBase):
    event_id: int


class RegistrationPublic(RegistrationBase):
    id: int
    event_id: int
    confirmed: bool
    registered_at: datetime