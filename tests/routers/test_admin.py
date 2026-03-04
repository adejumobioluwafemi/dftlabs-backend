import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/admin/login",
        json={"password": "test-admin-password"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/admin/login",
        json={"password": "wrong"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_without_token(client: AsyncClient) -> None:
    resp = await client.get("/api/blog/admin/drafts")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_with_token(
    client: AsyncClient, auth_headers: dict
) -> None:
    resp = await client.get("/api/blog/admin/drafts", headers=auth_headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"