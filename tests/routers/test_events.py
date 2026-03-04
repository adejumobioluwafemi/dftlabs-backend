import pytest
from httpx import AsyncClient

VALID_EVENT = {
    "slug": "ai-health-workshop-2026",
    "title": "AI in Healthcare Workshop",
    "event_type": "Workshop",
    "date": "Mar 22, 2026",
    "time": "9:00 AM – 5:00 PM WAT",
    "location": "Lagos, Nigeria",
    "price": "Free",
    "short_desc": "A full-day hands-on workshop on AI in clinical environments.",
    "description": "## About\n\nFull description here.",
    "max_spots": 40,
}


@pytest.mark.asyncio
async def test_list_events_empty(client: AsyncClient) -> None:
    resp = await client.get("/api/events/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_event_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/events/admin/", json=VALID_EVENT)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_and_get_event(
    client: AsyncClient, auth_headers: dict
) -> None:
    resp = await client.post(
        "/api/events/admin/", json=VALID_EVENT, headers=auth_headers
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["slug"] == "ai-health-workshop-2026"
    assert data["filled"] == 0
    assert data["max_spots"] == 40

    # Get by slug
    resp = await client.get("/api/events/ai-health-workshop-2026")
    assert resp.status_code == 200
    assert resp.json()["title"] == "AI in Healthcare Workshop"


@pytest.mark.asyncio
async def test_filled_count_increments(
    client: AsyncClient, auth_headers: dict
) -> None:
    create = await client.post(
        "/api/events/admin/", json=VALID_EVENT, headers=auth_headers
    )
    event_id = create.json()["id"]

    # Register someone
    await client.post(
        "/api/registrations/",
        json={
            "event_id": event_id,
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
        },
    )

    resp = await client.get("/api/events/ai-health-workshop-2026")
    assert resp.json()["filled"] == 1


@pytest.mark.asyncio
async def test_update_event(
    client: AsyncClient, auth_headers: dict
) -> None:
    create = await client.post(
        "/api/events/admin/", json=VALID_EVENT, headers=auth_headers
    )
    event_id = create.json()["id"]

    resp = await client.patch(
        f"/api/events/admin/{event_id}",
        json={"price": "₦15,000", "max_spots": 60},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["price"] == "₦15,000"
    assert resp.json()["max_spots"] == 60


@pytest.mark.asyncio
async def test_deactivate_event(
    client: AsyncClient, auth_headers: dict
) -> None:
    create = await client.post(
        "/api/events/admin/", json=VALID_EVENT, headers=auth_headers
    )
    event_id = create.json()["id"]

    await client.patch(
        f"/api/events/admin/{event_id}",
        json={"is_active": False},
        headers=auth_headers,
    )

    resp = await client.get("/api/events/")
    assert resp.json() == []


@pytest.mark.asyncio
async def test_delete_event(
    client: AsyncClient, auth_headers: dict
) -> None:
    create = await client.post(
        "/api/events/admin/", json=VALID_EVENT, headers=auth_headers
    )
    event_id = create.json()["id"]

    resp = await client.delete(
        f"/api/events/admin/{event_id}", headers=auth_headers
    )
    assert resp.status_code == 204

    resp = await client.get("/api/events/")
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_nonexistent_event(client: AsyncClient) -> None:
    resp = await client.get("/api/events/does-not-exist")
    assert resp.status_code == 404