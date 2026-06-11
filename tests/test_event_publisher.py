"""EventPublisherClient: retries, structured failures, and 502 mapping in routes."""

import uuid

import httpx
import pytest

from event_admin.adapters.event_publisher import EventPublisherClient
from event_admin.errors import EventPublishError


API_KEY = "receiver-key-0123456789abcdef"


def make_publisher(handler, attempts: int = 3) -> EventPublisherClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://receiver.test")
    return EventPublisherClient(http_client=http_client, api_key=API_KEY, attempts=attempts)


async def test_publish_success_sends_binary_cloudevent() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["url"] = str(request.url)
        return httpx.Response(202)

    publisher = make_publisher(handler)
    await publisher.publish(source="admin", event_type="user.email.change_requested", data={"x": 1})

    assert captured["url"].endswith("/event/admin")
    # event-receiver expects the raw key (no Bearer prefix) — see ingest_admin
    assert captured["headers"]["Authorization"] == API_KEY
    assert captured["headers"]["ce-type"] == "user.email.change_requested"
    assert captured["headers"]["ce-source"] == "admin"


async def test_publish_non_2xx_raises_event_publish_error_without_retry() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(401, text="bad key")

    publisher = make_publisher(handler)
    with pytest.raises(EventPublishError) as exc_info:
        await publisher.publish(source="admin", event_type="booking.client_reassigned", data={})

    assert exc_info.value.upstream_status == 401
    assert calls["count"] == 1  # HTTP errors are not retried


async def test_publish_transport_error_is_retried_then_raises() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        raise httpx.ConnectError("connection refused", request=request)

    publisher = make_publisher(handler, attempts=2)
    with pytest.raises(EventPublishError) as exc_info:
        await publisher.publish(source="admin", event_type="user.email.change_requested", data={})

    assert exc_info.value.upstream_status is None
    assert calls["count"] == 2


async def test_publish_recovers_on_retry() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(202)

    publisher = make_publisher(handler, attempts=3)
    await publisher.publish(source="admin", event_type="user.email.change_requested", data={})
    assert calls["count"] == 2


async def test_change_email_returns_502_when_publish_fails(client, admin_headers, fakes) -> None:
    user_id = uuid.uuid4()
    fakes.users_client.users_by_id[user_id] = {"id": str(user_id), "email": "old@x.com", "role": "client"}
    fakes.publisher.error = EventPublishError(
        event_type="user.email.change_requested",
        source="admin",
        upstream_status=503,
        detail="event-receiver returned 503",
    )

    response = await client.post(
        f"/api/users/id/{user_id}/change-email",
        json={"new_email": "new@x.com"},
        headers=admin_headers,
    )

    assert response.status_code == 502
    body = response.json()
    assert body["upstream_status"] == 503
    assert "NOT applied" in body["detail"]
