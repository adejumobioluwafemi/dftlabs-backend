import pytest
from httpx import AsyncClient


VALID_POST = {
    "slug": "test-post-001",
    "title": "Test Blog Post",
    "tag": "Research Digest",
    "excerpt": "A short excerpt for testing.",
    "content": "## Overview\n\nFull content here.",
    "status": "draft",
}


@pytest.mark.asyncio
async def test_list_posts_empty(client: AsyncClient) -> None:
    resp = await client.get("/api/blog/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_post_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/blog/admin/", json=VALID_POST)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_and_get_post(
    client: AsyncClient, auth_headers: dict
) -> None:
    # Create
    resp = await client.post(
        "/api/blog/admin/", json=VALID_POST, headers=auth_headers
    )
    assert resp.status_code == 201
    created = resp.json()
    assert created["slug"] == "test-post-001"
    assert created["status"] == "draft"

    # Draft not visible publicly
    resp = await client.get("/api/blog/test-post-001")
    assert resp.status_code == 404

    # Publish it
    resp = await client.patch(
        f"/api/blog/admin/{created['id']}",
        json={"status": "published"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["published_at"] is not None

    # Now visible publicly
    resp = await client.get("/api/blog/test-post-001")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Test Blog Post"


@pytest.mark.asyncio
async def test_list_only_published(
    client: AsyncClient, auth_headers: dict
) -> None:
    # Create draft
    await client.post(
        "/api/blog/admin/", json=VALID_POST, headers=auth_headers
    )
    # Public list should be empty
    resp = await client.get("/api/blog/")
    assert resp.json() == []


@pytest.mark.asyncio
async def test_delete_post(
    client: AsyncClient, auth_headers: dict
) -> None:
    create_resp = await client.post(
        "/api/blog/admin/", json=VALID_POST, headers=auth_headers
    )
    post_id = create_resp.json()["id"]

    del_resp = await client.delete(
        f"/api/blog/admin/{post_id}", headers=auth_headers
    )
    assert del_resp.status_code == 204

    # Confirm gone
    resp = await client.get(f"/api/blog/admin/drafts", headers=auth_headers)
    assert all(p["id"] != post_id for p in resp.json())


@pytest.mark.asyncio
async def test_list_drafts_admin(
    client: AsyncClient, auth_headers: dict
) -> None:
    await client.post(
        "/api/blog/admin/", json=VALID_POST, headers=auth_headers
    )
    resp = await client.get("/api/blog/admin/drafts", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["status"] == "draft"


@pytest.mark.asyncio
async def test_invalid_status_rejected(
    client: AsyncClient, auth_headers: dict
) -> None:
    create = await client.post(
        "/api/blog/admin/", json=VALID_POST, headers=auth_headers
    )
    post_id = create.json()["id"]
    resp = await client.patch(
        f"/api/blog/admin/{post_id}",
        json={"status": "invalid-status"},
        headers=auth_headers,
    )
    assert resp.status_code == 422