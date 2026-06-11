"""POST /api/users/id/{id}/change-email: validation matrix and casing normalization."""

import uuid

import pytest

from tests.test_users_proxy import make_upstream_user


@pytest.fixture
def client_user(fakes) -> uuid.UUID:
    user_id = uuid.uuid4()
    fakes.users_client.users_by_id[user_id] = make_upstream_user(user_id)
    return user_id


async def test_change_email_publishes_lowercased_payload(client, admin_headers, fakes, client_user) -> None:
    response = await client.post(
        f"/api/users/id/{client_user}/change-email",
        json={"new_email": "New.Client+Tag@Example.COM"},
        headers=admin_headers,
    )

    assert response.status_code == 202
    assert len(fakes.publisher.published) == 1
    event = fakes.publisher.published[0]
    assert event["event_type"] == "user.email.change_requested"
    assert event["data"]["new_email"] == "new.client+tag@example.com"
    assert event["data"]["old_email"] == "client@example.com"
    assert event["data"]["user_id"] == str(client_user)
    assert event["data"]["requested_by"] == "admin@test.local"


async def test_change_email_unknown_user_404(client, admin_headers, fakes) -> None:
    response = await client.post(
        f"/api/users/id/{uuid.uuid4()}/change-email",
        json={"new_email": "x@example.com"},
        headers=admin_headers,
    )
    assert response.status_code == 404
    assert fakes.publisher.published == []


async def test_change_email_non_client_role_400(client, admin_headers, fakes) -> None:
    user_id = uuid.uuid4()
    fakes.users_client.users_by_id[user_id] = make_upstream_user(user_id, role="organizer")

    response = await client.post(
        f"/api/users/id/{user_id}/change-email",
        json={"new_email": "x@example.com"},
        headers=admin_headers,
    )
    assert response.status_code == 400


async def test_change_email_same_email_case_insensitive_400(client, admin_headers, fakes, client_user) -> None:
    response = await client.post(
        f"/api/users/id/{client_user}/change-email",
        json={"new_email": "CLIENT@example.com"},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert fakes.publisher.published == []


async def test_change_email_taken_email_409_checked_lowercased(client, admin_headers, fakes, client_user) -> None:
    fakes.users_client.users_by_email_role[("taken@example.com", "client")] = {"id": str(uuid.uuid4())}

    response = await client.post(
        f"/api/users/id/{client_user}/change-email",
        json={"new_email": "Taken@Example.com"},
        headers=admin_headers,
    )
    assert response.status_code == 409
    assert fakes.publisher.published == []
