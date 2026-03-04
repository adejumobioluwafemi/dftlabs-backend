import pytest
from httpx import AsyncClient

EVENT_PAYLOAD = {
    "slug": "open-day-may26",
    "title": "DFT Labs Open Day",
    "event_type": "Open Day",
    "date": "May 3, 2026",
    "time": "2:00 PM – 6:00 PM WAT",
    "location": "Virtual",
    "price": "Free",
    "short_desc": "Quarterly open day.",
    "description": "## About\n\nJoin us virtually.",
    "max_spots": 5,  # Small for capacity tests
}

REG_PAYLOAD = {
    "first_name": "Femi",
    "last_name": "Adeyemi",
    "email": "femi@example.com",
}


async def _create_event(client: AsyncClient, headers: dict) -> int:
    resp = await client.post(
        "/api/events/admin/", json=EVENT_PAYLOAD, headers=headers
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_register_success(
    client: AsyncClient, auth_headers: dict
) -> None:
    event_id = await _create_event(client, auth_headers)
    resp = await client.post(
        "/api/registrations/",
        json={**REG_PAYLOAD, "event_id": event_id},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "femi@example.com"
    assert data["confirmed"] is True


@pytest.mark.asyncio
async def test_duplicate_registration_rejected(
    client: AsyncClient, auth_headers: dict
) -> None:
    event_id = await _create_event(client, auth_headers)
    payload = {**REG_PAYLOAD, "event_id": event_id}

    await client.post("/api/registrations/", json=payload)
    resp = await client.post("/api/registrations/", json=payload)
    assert resp.status_code == 409
    assert "already registered" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_event_fully_booked(
    client: AsyncClient, auth_headers: dict
) -> None:
    event_id = await _create_event(client, auth_headers)

    # Fill all 5 spots
    for i in range(5):
        resp = await client.post(
            "/api/registrations/",
            json={
                "event_id": event_id,
                "first_name": f"User{i}",
                "last_name": "Test",
                "email": f"user{i}@example.com",
            },
        )
        assert resp.status_code == 201

    # 6th registration should fail
    resp = await client.post(
        "/api/registrations/",
        json={
            "event_id": event_id,
            "first_name": "Extra",
            "last_name": "Person",
            "email": "extra@example.com",
        },
    )
    assert resp.status_code == 409
    assert "fully booked" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_register_nonexistent_event(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/registrations/",
        json={**REG_PAYLOAD, "event_id": 99999},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_get_registrations(
    client: AsyncClient, auth_headers: dict
) -> None:
    event_id = await _create_event(client, auth_headers)
    await client.post(
        "/api/registrations/",
        json={**REG_PAYLOAD, "event_id": event_id},
    )

    resp = await client.get(
        f"/api/registrations/admin/event/{event_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["email"] == "femi@example.com"


@pytest.mark.asyncio
async def test_admin_registrations_requires_auth(
    client: AsyncClient, auth_headers: dict
) -> None:
    event_id = await _create_event(client, auth_headers)
    resp = await client.get(f"/api/registrations/admin/event/{event_id}")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_virtual_registration(
    client: AsyncClient, auth_headers: dict
) -> None:
    event_id = await _create_event(client, auth_headers)
    resp = await client.post(
        "/api/registrations/",
        json={**REG_PAYLOAD, "event_id": event_id, "is_virtual": True},
    )
    assert resp.status_code == 201
    assert resp.json()["is_virtual"] is True