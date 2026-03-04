from datetime import datetime, UTC
from typing import Annotated, Optional

from pydantic import field_validator
from sqlmodel import Field, SQLModel


class BlogPostBase(SQLModel):
    title: str = Field(min_length=1, max_length=500)
    tag: str = Field(max_length=100)
    excerpt: str = Field(min_length=1)
    content: str = Field(min_length=1)
    image: Optional[str] = Field(default=None, max_length=500)
    author: str = Field(default="DFT Labs Team", max_length=200)
    read_time: str = Field(default="5 min", max_length=50)
    sources: Optional[str] = Field(default=None)
    status: str = Field(default="draft", max_length=50)
    agent_generated: bool = Field(default=False)


class BlogPost(BlogPostBase, table=True):
    __tablename__ = "blog_posts" # type: ignore

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(max_length=200, unique=True, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
    published_at: Optional[datetime] = Field(default=None)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class BlogPostCreate(BlogPostBase):
    slug: str = Field(max_length=200)


class BlogPostUpdate(SQLModel):
    title: Optional[str] = Field(default=None, max_length=500)
    tag: Optional[str] = Field(default=None, max_length=100)
    excerpt: Optional[str] = Field(default=None)
    content: Optional[str] = Field(default=None)
    image: Optional[str] = Field(default=None, max_length=500)
    read_time: Optional[str] = Field(default=None, max_length=50)
    status: Optional[str] = Field(default=None, max_length=50)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        allowed = {"draft", "published", "archived"}
        if v is not None and v not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return v


class BlogPostPublic(BlogPostBase):
    id: int
    slug: str
    created_at: datetime
    published_at: Optional[datetime] = None
    updated_at: datetime