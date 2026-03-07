# app/models/product.py
from datetime import datetime, UTC
from typing import Optional

from pydantic import field_validator
from sqlmodel import Field, SQLModel


# ── Serialisation helpers ─────────────────────────────────────────────────────

def _join(items: list[str] | None) -> str:
    """['a', 'b'] → 'a\nb'"""
    return "\n".join(items) if items else ""


def _split(raw: str | None) -> list[str]:
    """'a\nb' → ['a', 'b']"""
    if not raw:
        return []
    return [l.strip() for l in raw.split("\n") if l.strip()]


def _join_metrics(metrics: list[list[str]] | None) -> str:
    """[['94%','Accuracy'], ...] → '94%;Accuracy\n...'"""
    if not metrics:
        return ""
    return "\n".join(
        f"{m[0]};{m[1]}" for m in metrics if len(m) >= 2
    )


def _split_metrics(raw: str | None) -> list[list[str]]:
    """'94%;Accuracy\n...' → [['94%','Accuracy'], ...]"""
    if not raw:
        return []
    result = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split(";", 1)
        result.append([parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""])
    return result


# ── DB Table ──────────────────────────────────────────────────────────────────

class Product(SQLModel, table=True):
    __tablename__ = "products"  # type: ignore

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(max_length=200, unique=True, index=True)
    name: str = Field(max_length=200)
    sector: str = Field(max_length=100)
    status: str = Field(max_length=50)
    tagline: str = Field(max_length=500)
    desc: str = Field(default="")
    version: str = Field(default="", max_length=50)
    icon: str = Field(default="🔷", max_length=20)
    image: Optional[str] = Field(default=None, max_length=500)

    # Lists serialised as newline strings; metrics as "val;label\n..."
    metrics_raw: str = Field(default="")
    features_raw: str = Field(default="")
    use_cases_raw: str = Field(default="")
    tech_raw: str = Field(default="")

    cta: str = Field(default="Request Demo", max_length=100)
    cta_url: str = Field(default="", max_length=500)
    is_visible: bool = Field(default=True)
    order_index: int = Field(default=0)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None)
    )


# ── Create schema ─────────────────────────────────────────────────────────────

class ProductCreate(SQLModel):
    slug: str = Field(max_length=200)
    name: str = Field(min_length=1, max_length=200)
    sector: str = Field(max_length=100)
    status: str = Field(max_length=50)
    tagline: str = Field(min_length=1, max_length=500)
    desc: str = Field(default="")
    version: str = Field(default="", max_length=50)
    icon: str = Field(default="🔷", max_length=20)
    image: Optional[str] = Field(default=None, max_length=500)

    metrics: list[list[str]] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    use_cases: list[str] = Field(default_factory=list)
    tech: list[str] = Field(default_factory=list)

    cta: str = Field(default="Request Demo", max_length=100)
    cta_url: str = Field(default="", max_length=500)
    is_visible: bool = Field(default=True)
    order_index: int = Field(default=0)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"Live", "Beta", "Coming Soon"}
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return v

    @field_validator("sector")
    @classmethod
    def validate_sector(cls, v: str) -> str:
        allowed = {"Healthcare", "Agriculture", "Banking", "Education", "General"}
        if v not in allowed:
            raise ValueError(f"sector must be one of {allowed}")
        return v


# ── Update schema ─────────────────────────────────────────────────────────────

class ProductUpdate(SQLModel):
    name: Optional[str] = Field(default=None, max_length=200)
    sector: Optional[str] = Field(default=None, max_length=100)
    status: Optional[str] = Field(default=None, max_length=50)
    tagline: Optional[str] = Field(default=None, max_length=500)
    desc: Optional[str] = None
    version: Optional[str] = Field(default=None, max_length=50)
    icon: Optional[str] = Field(default=None, max_length=20)
    image: Optional[str] = Field(default=None, max_length=500)

    metrics: Optional[list[list[str]]] = None
    features: Optional[list[str]] = None
    use_cases: Optional[list[str]] = None
    tech: Optional[list[str]] = None

    cta: Optional[str] = Field(default=None, max_length=100)
    cta_url: Optional[str] = Field(default=None, max_length=500)
    is_visible: Optional[bool] = None
    order_index: Optional[int] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        allowed = {"Live", "Beta", "Coming Soon"}
        if v is not None and v not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return v

    @field_validator("sector")
    @classmethod
    def validate_sector(cls, v: Optional[str]) -> Optional[str]:
        allowed = {"Healthcare", "Agriculture", "Banking", "Education", "General"}
        if v is not None and v not in allowed:
            raise ValueError(f"sector must be one of {allowed}")
        return v


# ── Public response schema ─────────────────────────────────────────────────────

class ProductPublic(SQLModel):
    id: int
    slug: str
    name: str
    sector: str
    status: str
    tagline: str
    desc: str
    version: str
    icon: str
    image: Optional[str]
    metrics: list[list[str]]
    features: list[str]
    use_cases: list[str]
    tech: list[str]
    cta: str
    cta_url: str
    is_visible: bool
    order_index: int
    created_at: datetime
    updated_at: datetime


def product_to_public(p: Product) -> ProductPublic:
    """Convert a Product ORM row → ProductPublic (deserialising raw strings)."""
    return ProductPublic(
        id=p.id,  # type: ignore[arg-type]
        slug=p.slug,
        name=p.name,
        sector=p.sector,
        status=p.status,
        tagline=p.tagline,
        desc=p.desc,
        version=p.version,
        icon=p.icon,
        image=p.image,
        metrics=_split_metrics(p.metrics_raw),
        features=_split(p.features_raw),
        use_cases=_split(p.use_cases_raw),
        tech=_split(p.tech_raw),
        cta=p.cta,
        cta_url=p.cta_url,
        is_visible=p.is_visible,
        order_index=p.order_index,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def create_product_from_schema(data: ProductCreate) -> Product:
    """Serialise list fields → raw strings, return an unsaved Product."""
    return Product(
        slug=data.slug,
        name=data.name,
        sector=data.sector,
        status=data.status,
        tagline=data.tagline,
        desc=data.desc,
        version=data.version,
        icon=data.icon,
        image=data.image,
        metrics_raw=_join_metrics(data.metrics),
        features_raw=_join(data.features),
        use_cases_raw=_join(data.use_cases),
        tech_raw=_join(data.tech),
        cta=data.cta,
        cta_url=data.cta_url,
        is_visible=data.is_visible,
        order_index=data.order_index,
    )