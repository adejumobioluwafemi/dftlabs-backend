# tests/routers/test_products.py
"""
Tests for GET /api/products/  GET /api/products/{slug}
       POST/GET/PATCH/DELETE /api/products/admin/...

Run with:
    pytest tests/routers/test_products.py -v
"""
import pytest
from httpx import AsyncClient


# ── Fixtures ──────────────────────────────────────────────────────────────────

PRODUCT_PAYLOAD = {
    "slug": "medscan-ai",
    "name": "MedScan AI",
    "sector": "Healthcare",
    "status": "Live",
    "tagline": "Real-time medical image analysis at clinical scale",
    "desc": "MedScan AI is a deep-learning platform for radiology triage.",
    "version": "v1.0",
    "icon": "🫁",
    "image": None,
    "metrics": [["94%", "Accuracy"], ["<200ms", "Latency"]],
    "features": [
        "Multi-organ scan analysis",
        "DICOM & HL7 FHIR integration",
    ],
    "use_cases": [
        "Radiology triage prioritization",
        "Remote diagnostics",
    ],
    "tech": ["PyTorch", "FastAPI", "DICOM"],
    "cta": "Request Demo",
    "cta_url": "/contact",
    "is_visible": True,
    "order_index": 1,
}


# ── Admin CRUD ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_create_product(client: AsyncClient, admin_token: str) -> None:
    resp = await client.post(
        "/api/products/admin/",
        json=PRODUCT_PAYLOAD,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["slug"] == "medscan-ai"
    assert data["name"] == "MedScan AI"
    assert data["metrics"] == [["94%", "Accuracy"], ["<200ms", "Latency"]]
    assert "PyTorch" in data["tech"]
    assert data["is_visible"] is True


@pytest.mark.asyncio
async def test_admin_create_duplicate_slug(client: AsyncClient, admin_token: str) -> None:
    headers = {"Authorization": f"Bearer {admin_token}"}
    await client.post("/api/products/admin/", json=PRODUCT_PAYLOAD, headers=headers)
    resp = await client.post("/api/products/admin/", json=PRODUCT_PAYLOAD, headers=headers)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_admin_create_invalid_status(client: AsyncClient, admin_token: str) -> None:
    bad = {**PRODUCT_PAYLOAD, "slug": "bad-product", "status": "Deprecated"}
    resp = await client.post(
        "/api/products/admin/",
        json=bad,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_admin_list_all_products(client: AsyncClient, admin_token: str) -> None:
    headers = {"Authorization": f"Bearer {admin_token}"}
    await client.post("/api/products/admin/", json=PRODUCT_PAYLOAD, headers=headers)
    resp = await client.get("/api/products/admin/", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_admin_update_product(client: AsyncClient, admin_token: str) -> None:
    headers = {"Authorization": f"Bearer {admin_token}"}
    create_resp = await client.post("/api/products/admin/", json=PRODUCT_PAYLOAD, headers=headers)
    product_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/products/admin/{product_id}",
        json={"status": "Beta", "version": "v1.1"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "Beta"
    assert resp.json()["version"] == "v1.1"


@pytest.mark.asyncio
async def test_admin_hide_product(client: AsyncClient, admin_token: str) -> None:
    headers = {"Authorization": f"Bearer {admin_token}"}
    create_resp = await client.post("/api/products/admin/", json=PRODUCT_PAYLOAD, headers=headers)
    product_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/products/admin/{product_id}",
        json={"is_visible": False},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_visible"] is False


@pytest.mark.asyncio
async def test_admin_update_lists(client: AsyncClient, admin_token: str) -> None:
    """Verify metrics / features / tech can be replaced via PATCH."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    create_resp = await client.post("/api/products/admin/", json=PRODUCT_PAYLOAD, headers=headers)
    product_id = create_resp.json()["id"]

    new_metrics = [["99%", "Uptime"], ["5ms", "P99 latency"]]
    resp = await client.patch(
        f"/api/products/admin/{product_id}",
        json={"metrics": new_metrics, "tech": ["TensorFlow", "Redis"]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["metrics"] == new_metrics
    assert "TensorFlow" in resp.json()["tech"]


@pytest.mark.asyncio
async def test_admin_delete_product(client: AsyncClient, admin_token: str) -> None:
    headers = {"Authorization": f"Bearer {admin_token}"}
    create_resp = await client.post("/api/products/admin/", json=PRODUCT_PAYLOAD, headers=headers)
    product_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/products/admin/{product_id}", headers=headers)
    assert del_resp.status_code == 204

    # Verify gone from public listing
    list_resp = await client.get("/api/products/")
    assert all(p["id"] != product_id for p in list_resp.json())


# ── Auth guards ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_routes_require_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/products/admin/")).status_code == 401
    assert (await client.post("/api/products/admin/", json=PRODUCT_PAYLOAD)).status_code == 401
    assert (await client.patch("/api/products/admin/999", json={})).status_code == 401
    assert (await client.delete("/api/products/admin/999")).status_code == 401


# ── Public endpoints ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_public_list_only_visible(client: AsyncClient, admin_token: str) -> None:
    headers = {"Authorization": f"Bearer {admin_token}"}
    # Create visible
    await client.post("/api/products/admin/", json=PRODUCT_PAYLOAD, headers=headers)
    # Create hidden
    hidden = {**PRODUCT_PAYLOAD, "slug": "hidden-app", "is_visible": False}
    await client.post("/api/products/admin/", json=hidden, headers=headers)

    resp = await client.get("/api/products/")
    assert resp.status_code == 200
    slugs = [p["slug"] for p in resp.json()]
    assert "medscan-ai" in slugs
    assert "hidden-app" not in slugs


@pytest.mark.asyncio
async def test_public_get_by_slug(client: AsyncClient, admin_token: str) -> None:
    headers = {"Authorization": f"Bearer {admin_token}"}
    await client.post("/api/products/admin/", json=PRODUCT_PAYLOAD, headers=headers)

    resp = await client.get("/api/products/medscan-ai")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "MedScan AI"
    assert data["metrics"][0] == ["94%", "Accuracy"]
    assert data["features"][0] == "Multi-organ scan analysis"


@pytest.mark.asyncio
async def test_public_get_hidden_returns_404(client: AsyncClient, admin_token: str) -> None:
    headers = {"Authorization": f"Bearer {admin_token}"}
    hidden = {**PRODUCT_PAYLOAD, "slug": "secret-app", "is_visible": False}
    await client.post("/api/products/admin/", json=hidden, headers=headers)

    resp = await client.get("/api/products/secret-app")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_public_filter_by_sector(client: AsyncClient, admin_token: str) -> None:
    headers = {"Authorization": f"Bearer {admin_token}"}
    await client.post("/api/products/admin/", json=PRODUCT_PAYLOAD, headers=headers)
    ag = {**PRODUCT_PAYLOAD, "slug": "cropmind", "name": "CropMind", "sector": "Agriculture"}
    await client.post("/api/products/admin/", json=ag, headers=headers)

    resp = await client.get("/api/products/?sector=Healthcare")
    assert resp.status_code == 200
    assert all(p["sector"] == "Healthcare" for p in resp.json())


@pytest.mark.asyncio
async def test_public_filter_by_status(client: AsyncClient, admin_token: str) -> None:
    headers = {"Authorization": f"Bearer {admin_token}"}
    await client.post("/api/products/admin/", json=PRODUCT_PAYLOAD, headers=headers)
    beta = {**PRODUCT_PAYLOAD, "slug": "beta-app", "status": "Beta"}
    await client.post("/api/products/admin/", json=beta, headers=headers)

    resp = await client.get("/api/products/?status=Live")
    assert resp.status_code == 200
    assert all(p["status"] == "Live" for p in resp.json())


@pytest.mark.asyncio
async def test_public_get_nonexistent_slug(client: AsyncClient) -> None:
    resp = await client.get("/api/products/does-not-exist")
    assert resp.status_code == 404