"""Blacklist API: CRUD, auth, effectiveness logic, pagination, and adapter SQL."""

import dataclasses
import datetime as dt
import uuid
from typing import Any

from event_admin.adapters.blacklist_db import BlacklistDBAdapter
from event_admin.dto.blacklist import BlacklistCreateDto, BlacklistListFiltersDto, BlacklistUpdateDto


NOW = dt.datetime(2026, 6, 11, 12, 0, tzinfo=dt.UTC)

SERVICE_HEADERS = {"Authorization": "Bearer blacklist-token-0123456789abcdef"}


def make_create_dto(**overrides: Any) -> BlacklistCreateDto:
    defaults: dict[str, Any] = {
        "field": "client_email",
        "value": "spam@example.com",
        "is_active": True,
        "active_from": None,
        "active_until": None,
        "comment": None,
        "created_by": "admin@test.local",
    }
    defaults.update(overrides)
    return BlacklistCreateDto(**defaults)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


async def test_crud_requires_jwt(client) -> None:
    response = await client.get("/api/blacklist")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "missing_bearer_token"


async def test_crud_requires_admin_role(client, user_headers) -> None:
    response = await client.get("/api/blacklist", headers=user_headers)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "admin_access_required"


async def test_active_endpoint_rejects_missing_token(client) -> None:
    response = await client.get("/api/blacklist/active")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_service_token"


async def test_active_endpoint_rejects_wrong_token(client) -> None:
    response = await client.get("/api/blacklist/active", headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_service_token"


async def test_active_endpoint_rejects_admin_jwt(client, admin_headers) -> None:
    """Admin JWT is not a valid service token (separate credentials)."""
    response = await client.get("/api/blacklist/active", headers=admin_headers)
    assert response.status_code == 401


async def test_active_endpoint_accepts_service_token(client, fakes) -> None:
    await fakes.blacklist_db.create_entry(make_create_dto())
    response = await client.get("/api/blacklist/active", headers=SERVICE_HEADERS)
    assert response.status_code == 200
    assert response.json() == {"field": "client_email", "values": ["spam@example.com"]}


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def test_create_entry_returns_201_and_lowercases_email(client, admin_headers) -> None:
    response = await client.post(
        "/api/blacklist",
        json={"value": "Spam@Example.COM", "comment": "abuse"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["field"] == "client_email"
    assert body["value"] == "spam@example.com"
    assert body["is_active"] is True
    assert body["comment"] == "abuse"
    assert body["created_by"] == "admin@test.local"


async def test_create_entry_rejects_inverted_window(client, admin_headers) -> None:
    response = await client.post(
        "/api/blacklist",
        json={
            "value": "spam@example.com",
            "active_from": "2026-06-20T00:00:00Z",
            "active_until": "2026-06-10T00:00:00Z",
        },
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_active_window"


async def test_patch_updates_entry(client, admin_headers, fakes) -> None:
    entry = await fakes.blacklist_db.create_entry(make_create_dto())
    response = await client.patch(
        f"/api/blacklist/{entry.id}",
        json={"is_active": False, "comment": "paused"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_active"] is False
    assert body["comment"] == "paused"
    assert body["value"] == "spam@example.com"


async def test_patch_lowercases_new_email_value(client, admin_headers, fakes) -> None:
    entry = await fakes.blacklist_db.create_entry(make_create_dto())
    response = await client.patch(
        f"/api/blacklist/{entry.id}",
        json={"value": "Другой@Example.COM"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["value"] == "другой@example.com"


async def test_patch_unknown_entry_returns_404(client, admin_headers) -> None:
    response = await client.patch(
        f"/api/blacklist/{uuid.uuid4()}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "blacklist_entry_not_found"


async def test_patch_empty_body_returns_400(client, admin_headers, fakes) -> None:
    entry = await fakes.blacklist_db.create_entry(make_create_dto())
    response = await client.patch(f"/api/blacklist/{entry.id}", json={}, headers=admin_headers)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "empty_update"


async def test_patch_null_value_returns_400(client, admin_headers, fakes) -> None:
    entry = await fakes.blacklist_db.create_entry(make_create_dto())
    response = await client.patch(f"/api/blacklist/{entry.id}", json={"value": None}, headers=admin_headers)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "field_not_nullable"


async def test_delete_entry(client, admin_headers, fakes) -> None:
    entry = await fakes.blacklist_db.create_entry(make_create_dto())
    response = await client.delete(f"/api/blacklist/{entry.id}", headers=admin_headers)
    assert response.status_code == 204
    assert fakes.blacklist_db.entries == {}


async def test_delete_unknown_entry_returns_404(client, admin_headers) -> None:
    response = await client.delete(f"/api/blacklist/{uuid.uuid4()}", headers=admin_headers)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "blacklist_entry_not_found"


# ---------------------------------------------------------------------------
# Listing endpoints (pagination and filters)
# ---------------------------------------------------------------------------


async def test_list_pagination(client, admin_headers, fakes) -> None:
    for i in range(5):
        fakes.blacklist_db.now = NOW + dt.timedelta(minutes=i)
        await fakes.blacklist_db.create_entry(make_create_dto(value=f"user{i}@example.com"))

    response = await client.get("/api/blacklist?limit=2&offset=2", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 2
    # Newest first: user4, user3 | user2, user1 | user0
    assert [item["value"] for item in body["items"]] == ["user2@example.com", "user1@example.com"]


async def test_list_filters_by_value_substring(client, admin_headers, fakes) -> None:
    await fakes.blacklist_db.create_entry(make_create_dto(value="alice@corp.com"))
    await fakes.blacklist_db.create_entry(make_create_dto(value="bob@example.com"))

    response = await client.get("/api/blacklist?value=corp", headers=admin_headers)
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["value"] == "alice@corp.com"


async def test_list_only_effective_excludes_inactive_and_expired(client, admin_headers, fakes) -> None:
    await fakes.blacklist_db.create_entry(make_create_dto(value="effective@example.com"))
    await fakes.blacklist_db.create_entry(make_create_dto(value="disabled@example.com", is_active=False))
    await fakes.blacklist_db.create_entry(
        make_create_dto(value="expired@example.com", active_until=NOW - dt.timedelta(days=1)),
    )
    await fakes.blacklist_db.create_entry(
        make_create_dto(value="future@example.com", active_from=NOW + dt.timedelta(days=1)),
    )

    response = await client.get("/api/blacklist?only_effective=true", headers=admin_headers)
    body = response.json()
    assert body["total"] == 1
    assert [item["value"] for item in body["items"]] == ["effective@example.com"]

    response_all = await client.get("/api/blacklist", headers=admin_headers)
    assert response_all.json()["total"] == 4


async def test_active_endpoint_applies_effectiveness(client, fakes) -> None:
    await fakes.blacklist_db.create_entry(make_create_dto(value="effective@example.com"))
    await fakes.blacklist_db.create_entry(make_create_dto(value="disabled@example.com", is_active=False))
    await fakes.blacklist_db.create_entry(
        make_create_dto(value="expired@example.com", active_until=NOW - dt.timedelta(days=1)),
    )
    await fakes.blacklist_db.create_entry(make_create_dto(field="client_phone", value="+700000000"))

    response = await client.get("/api/blacklist/active?field=client_email", headers=SERVICE_HEADERS)
    assert response.json() == {"field": "client_email", "values": ["effective@example.com"]}


# ---------------------------------------------------------------------------
# Adapter SQL (recording executor; no DB)
# ---------------------------------------------------------------------------

ENTRY_ROW = {
    "id": uuid.uuid4(),
    "field": "client_email",
    "value": "spam@example.com",
    "is_active": True,
    "active_from": None,
    "active_until": None,
    "comment": None,
    "created_by": "admin@test.local",
    "created_at": NOW,
    "updated_at": NOW,
}


class RecordingSqlExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    async def fetch_one(self, query: str, values: dict) -> dict[str, Any] | None:
        self.calls.append(("fetch_one", query, values))
        if "count(*)" in query:
            return {"total": 1}
        return dict(ENTRY_ROW)

    async def fetch_all(self, query: str, values: dict) -> list[dict[str, Any]]:
        self.calls.append(("fetch_all", query, values))
        return [dict(ENTRY_ROW)]

    async def execute(self, query: str, values: dict) -> dict[str, Any] | None:
        self.calls.append(("execute", query, values))
        return dict(ENTRY_ROW)


async def test_adapter_effectiveness_is_evaluated_in_sql() -> None:
    executor = RecordingSqlExecutor()
    adapter = BlacklistDBAdapter(executor)

    await adapter.list_active_values("client_email")

    _, query, values = executor.calls[0]
    assert "is_active" in query
    assert "active_from IS NULL OR active_from <= now()" in query
    assert "active_until IS NULL OR active_until >= now()" in query
    assert values == {"field": "client_email"}


async def test_adapter_list_builds_filters_and_pagination() -> None:
    executor = RecordingSqlExecutor()
    adapter = BlacklistDBAdapter(executor)

    entries, total = await adapter.list_entries(
        BlacklistListFiltersDto(field="client_email", value_contains="a_b%c", only_effective=True),
        limit=10,
        offset=20,
    )

    assert total == 1
    assert len(entries) == 1
    count_call, list_call = executor.calls
    assert "count(*)" in count_call[1]
    assert "LIMIT :limit OFFSET :offset" in list_call[1]
    assert list_call[2]["limit"] == 10
    assert list_call[2]["offset"] == 20
    # LIKE wildcards in user input are escaped
    assert list_call[2]["value_contains"] == "a\\_b\\%c"
    assert "is_active" in list_call[1]


async def test_adapter_update_only_touches_provided_fields() -> None:
    executor = RecordingSqlExecutor()
    adapter = BlacklistDBAdapter(executor)

    await adapter.update_entry(ENTRY_ROW["id"], BlacklistUpdateDto(is_active=False, comment=None))

    _, query, values = executor.calls[0]
    assert "is_active = :is_active" in query
    assert "comment = :comment" in query
    assert "updated_at = now()" in query
    assert "value = :value" not in query
    assert "field = :field" not in query
    assert values == {"is_active": False, "comment": None, "entry_id": ENTRY_ROW["id"]}


async def test_adapter_create_maps_row_to_dto() -> None:
    executor = RecordingSqlExecutor()
    adapter = BlacklistDBAdapter(executor)

    dto = await adapter.create_entry(make_create_dto())

    assert dto.value == "spam@example.com"
    assert dataclasses.asdict(dto)["created_by"] == "admin@test.local"
    _, query, _ = executor.calls[0]
    assert "INSERT INTO blacklist_entries" in query
    assert "RETURNING" in query
