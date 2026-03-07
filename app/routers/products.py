# app/routers/products.py
import logging
from datetime import datetime, UTC
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.jwt import AdminDep
from app.database import get_session
from app.models.product import (
    Product,
    ProductCreate,
    ProductPublic,
    ProductUpdate,
    _join,
    _join_metrics,
    create_product_from_schema,
    product_to_public,
)
from app.services.cache_service import cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/products", tags=["Products"])
DBSession = Annotated[AsyncSession, Depends(get_session)]


# ── Public endpoints ──────────────────────────────────────────────────────────

@router.get("/", response_model=list[ProductPublic])
async def list_products(
    db: DBSession,
    sector: str | None = Query(None),
    status: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[ProductPublic]:
    """List all visible products, ordered by order_index then name."""
    cache_key = f"products:public:{sector}:{status}:{limit}:{offset}"
    if cached := cache.get(cache_key):
        return cached

    stmt = (
        select(Product)
        .where(Product.is_visible == True)  # noqa: E712
        .order_by(Product.order_index, Product.name)  # type: ignore[arg-type]
        .limit(limit)
        .offset(offset)
    )
    if sector:
        stmt = stmt.where(Product.sector == sector)
    if status:
        stmt = stmt.where(Product.status == status)

    rows = (await db.exec(stmt)).all()
    result = [product_to_public(p) for p in rows]
    cache.set(cache_key, result, ttl=300)
    logger.debug("Listed %d public products", len(result))
    return result


@router.get("/{slug}", response_model=ProductPublic)
async def get_product(slug: str, db: DBSession) -> ProductPublic:
    """Get a single visible product by slug."""
    cache_key = f"products:slug:{slug}"
    if cached := cache.get(cache_key):
        return cached

    row = (
        await db.exec(
            select(Product).where(
                Product.slug == slug,
                Product.is_visible == True,  # noqa: E712
            )
        )
    ).first()

    if not row:
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    result = product_to_public(row)
    cache.set(cache_key, result, ttl=600)
    return result


# ── Admin endpoints ───────────────────────────────────────────────────────────

@router.get("/admin/", response_model=list[ProductPublic])
async def admin_list_products(
    db: DBSession,
    _: AdminDep,
    sector: str | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[ProductPublic]:
    """Admin: list ALL products (visible + hidden), ordered by order_index."""
    stmt = (
        select(Product)
        .order_by(Product.order_index, Product.name)  # type: ignore[arg-type]
        .limit(limit)
        .offset(offset)
    )
    if sector:
        stmt = stmt.where(Product.sector == sector)

    rows = (await db.exec(stmt)).all()
    return [product_to_public(p) for p in rows]


@router.post(
    "/admin/",
    response_model=ProductPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_product(
    data: ProductCreate,
    db: DBSession,
    _: AdminDep,
) -> ProductPublic:
    """Admin: create a new product."""
    # Check slug uniqueness
    existing = (
        await db.exec(select(Product).where(Product.slug == data.slug))
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A product with slug '{data.slug}' already exists.",
        )

    product = create_product_from_schema(data)
    db.add(product)
    await db.flush()
    await db.refresh(product)
    cache.invalidate("products:")
    logger.info("Admin: created product slug=%s", product.slug)
    return product_to_public(product)


@router.patch("/admin/{product_id}", response_model=ProductPublic)
async def update_product(
    product_id: int,
    updates: ProductUpdate,
    db: DBSession,
    _: AdminDep,
) -> ProductPublic:
    """Admin: partial-update any product field including visibility."""
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    data = updates.model_dump(exclude_unset=True)

    # Handle list fields — convert to raw strings before setting
    if "metrics" in data:
        product.metrics_raw = _join_metrics(data.pop("metrics"))
    if "features" in data:
        product.features_raw = _join(data.pop("features"))
    if "use_cases" in data:
        product.use_cases_raw = _join(data.pop("use_cases"))
    if "tech" in data:
        product.tech_raw = _join(data.pop("tech"))

    # Apply remaining scalar fields
    for field, value in data.items():
        setattr(product, field, value)

    product.updated_at = datetime.now(UTC).replace(tzinfo=None)
    db.add(product)
    await db.flush()
    await db.refresh(product)
    cache.invalidate("products:")
    logger.info("Admin: updated product id=%d visible=%s", product_id, product.is_visible)
    return product_to_public(product)


@router.delete("/admin/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: int,
    db: DBSession,
    _: AdminDep,
) -> None:
    """Admin: permanently delete a product."""
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    await db.delete(product)
    cache.invalidate("products:")
    logger.info("Admin: deleted product id=%d", product_id)