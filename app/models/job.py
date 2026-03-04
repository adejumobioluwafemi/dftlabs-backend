from datetime import datetime, UTC
from typing import Optional

from sqlmodel import Field, SQLModel


class JobBase(SQLModel):
    role: str = Field(min_length=1, max_length=300)
    company: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1, max_length=200)
    job_type: str = Field(max_length=100)
    sector: str = Field(max_length=100)
    salary: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None)
    apply_url: Optional[str] = Field(default=None, max_length=500)
    source: Optional[str] = Field(default=None, max_length=200)


class Job(JobBase, table=True):
    __tablename__ = "jobs" # type: ignore

    id: Optional[int] = Field(default=None, primary_key=True)
    source_id: Optional[str] = Field(default=None, max_length=300, index=True)
    is_visible: bool = Field(default=True)
    is_featured: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
    expires_at: Optional[datetime] = Field(default=None)


class JobCreate(JobBase):
    source_id: Optional[str] = Field(default=None, max_length=300)


class JobUpdate(SQLModel):
    is_visible: Optional[bool] = Field(default=None)
    is_featured: Optional[bool] = Field(default=None)
    salary: Optional[str] = Field(default=None, max_length=200)


class JobPublic(JobBase):
    id: int
    is_visible: bool
    is_featured: bool
    created_at: datetime
    source_id: Optional[str] = None