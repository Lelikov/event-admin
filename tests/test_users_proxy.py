"""Users proxy endpoints: typed request/response models (no field passthrough)."""

import uuid

import httpx

from event_admin.adapters.users_client import UsersClient
from event_admin.services.users_cache import UsersCache


def make_upstream_user(user_id: uuid.UUID | None = None, **extra) -> dict:
    return {
        "id": str(user_id or uuid.uuid4()),
        "email": "client@example.com",
        "name": "Client",
        "role": "client",
        "time_zone": "Europe/Moscow",
        "contacts": [],
        "created_at": "2026-06-11T12:00:00Z",
        "updated_at": "2026-06-11T12:00:00Z",
        **extra,
    }


async def test_get_user_filters_unknown_upstream_fields(client, admin_headers, fakes) -> None:
    user_id = uuid.uuid4()
    fakes.users_client.users_by_id[user_id] = make_upstream_user(user_id, crm_internal_id="CRM-42")

    response = await client.get(f"/api/users/id/{user_id}", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(user_id)
    assert "crm_internal_id" not in body


async def test_by_ids_filters_unknown_upstream_fields(client, admin_headers, fakes) -> None:
    user_id = uuid.uuid4()
    fakes.users_client.users_by_id[user_id] = make_upstream_user(user_id, secret_flag=True)

    response = await client.post("/api/users/by-ids", json={"ids": [str(user_id)]}, headers=admin_headers)

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert "secret_flag" not in items[0]


async def test_by_ids_non_list_ids_returns_422(client, admin_headers) -> None:
    response = await client.post("/api/users/by-ids", json={"ids": 5}, headers=admin_headers)
    assert response.status_code == 422


async def test_by_ids_string_ids_returns_422(client, admin_headers) -> None:
    response = await client.post("/api/users/by-ids", json={"ids": "not-a-list"}, headers=admin_headers)
    assert response.status_code == 422


async def test_by_ids_invalid_uuid_returns_422(client, admin_headers) -> None:
    response = await client.post("/api/users/by-ids", json={"ids": ["nope"]}, headers=admin_headers)
    assert response.status_code == 422


async def test_by_ids_more_than_200_returns_422(client, admin_headers) -> None:
    ids = [str(uuid.uuid4()) for _ in range(201)]
    response = await client.post("/api/users/by-ids", json={"ids": ids}, headers=admin_headers)
    assert response.status_code == 422


async def test_list_users_response_is_typed(client, admin_headers, fakes) -> None:
    fakes.users_client.list_response = {
        "items": [make_upstream_user(extra_field="leak")],
        "total": 1,
        "limit": 50,
        "offset": 0,
        "internal_debug": "leak",
    }

    response = await client.get("/api/users", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert "internal_debug" not in body
    assert "extra_field" not in body["items"][0]


async def test_users_client_uses_by_identity_endpoint() -> None:
    """get_user_by_email_role must call /by-identity with query params."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://users.test")
    users_client = UsersClient(http_client=http_client, api_token="t", cache=UsersCache(ttl_seconds=1))

    result = await users_client.get_user_by_email_role("a+b@example.com", "client")

    assert result is None
    assert captured["path"] == "/api/users/by-identity"
    assert captured["params"] == {"email": "a+b@example.com", "role": "client"}
