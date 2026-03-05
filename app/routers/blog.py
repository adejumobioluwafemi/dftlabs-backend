# app/routers/blog.py

import logging
from datetime import datetime, UTC
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.jwt import AdminDep
from app.database import get_session
from app.models.blog import BlogPost, BlogPostCreate, BlogPostPublic, BlogPostUpdate
from app.services.cache_service import cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/blog", tags=["Blog"])
DBSession = Annotated[AsyncSession, Depends(get_session)]


# ── Public ────────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[BlogPostPublic])
async def list_posts(
    db: DBSession,
    tag: str | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
) -> list[BlogPost]:
    cache_key = f"blog:published:{tag}:{limit}:{offset}"
    if cached := cache.get(cache_key):
        return cached

    stmt = (
        select(BlogPost)
        .where(BlogPost.status == "published")
        .order_by(BlogPost.published_at.desc()) # type: ignore
        .limit(limit)
        .offset(offset)
    )
    if tag:
        stmt = stmt.where(BlogPost.tag == tag)

    result = (await db.exec(stmt)).all()
    cache.set(cache_key, result, ttl=300)
    logger.debug("Listed %d published posts (tag=%s)", len(result), tag)
    return result # type: ignore


@router.get("/{slug}", response_model=BlogPostPublic)
async def get_post(slug: str, db: DBSession) -> BlogPost:
    cache_key = f"blog:post:{slug}"
    if cached := cache.get(cache_key):
        return cached

    post = (
        await db.exec(
            select(BlogPost).where(
                BlogPost.slug == slug,
                BlogPost.status == "published",
            )
        )
    ).first()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    cache.set(cache_key, post, ttl=600)
    return post


# ── Admin ─────────────────────────────────────────────────────────────────────

@router.get("/admin/drafts", response_model=list[BlogPostPublic])
async def list_drafts(db: DBSession, _: AdminDep) -> list[BlogPost]:
    result = (
        await db.exec(
            select(BlogPost)
            .where(BlogPost.status == "draft")
            .order_by(BlogPost.created_at.desc()) # type: ignore
        )
    ).all()
    logger.debug("Admin: listed %d drafts", len(result))
    return result # type: ignore


@router.post(
    "/admin/",
    response_model=BlogPostPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_post(
    post: BlogPostCreate, db: DBSession, _: AdminDep
) -> BlogPost:
    db_post = BlogPost.model_validate(post)
    db.add(db_post)
    await db.flush()
    await db.refresh(db_post)
    cache.invalidate("blog:")
    logger.info("Admin: created post slug=%s", db_post.slug)
    return db_post


@router.patch("/admin/{post_id}", response_model=BlogPostPublic)
async def update_post(
    post_id: int,
    updates: BlogPostUpdate,
    db: DBSession,
    _: AdminDep,
) -> BlogPost:
    post = await db.get(BlogPost, post_id)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    for field_name, value in updates.model_dump(exclude_unset=True).items():
        setattr(post, field_name, value)

    if updates.status == "published" and not post.published_at:
        post.published_at = datetime.now(UTC).replace(tzinfo=None)

    post.updated_at = datetime.now(UTC).replace(tzinfo=None)
    db.add(post)
    await db.flush()
    await db.refresh(post)
    cache.invalidate("blog:")
    logger.info("Admin: updated post id=%d status=%s", post_id, post.status)
    return post


@router.delete("/admin/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: int, db: DBSession, _: AdminDep) -> None:
    post = await db.get(BlogPost, post_id)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )
    await db.delete(post)
    cache.invalidate("blog:")
    logger.info("Admin: deleted post id=%d", post_id)