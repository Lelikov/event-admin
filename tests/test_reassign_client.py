"""POST /bookings/{uid}/reassign-client: existence checks before publishing."""

import uuid

from event_admin.errors import EventPublishError
from tests.conftest import make_booking_details


async def test_reassign_unknown_booking_returns_404_and_publishes_nothing(client, admin_headers, fakes) -> None:
    fakes.users_client.users_by_email_role[("client@x.com", "client")] = {"id": str(uuid.uuid4())}

    response = await client.post(
        "/bookings/ghost-uid/reassign-client",
        json={"new_client_email": "client@x.com"},
        headers=admin_headers,
    )

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["code"] == "booking_not_found"
    assert "ghost-uid" in detail["message"]
    assert fakes.publisher.published == []


async def test_reassign_unknown_client_returns_404(client, admin_headers, fakes) -> None:
    fakes.bookings_controller.bookings["book-1"] = make_booking_details("book-1")

    response = await client.post(
        "/bookings/book-1/reassign-client",
        json={"new_client_email": "nobody@x.com"},
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "client_not_found"
    assert fakes.publisher.published == []


async def test_reassign_success_publishes_event(client, admin_headers, fakes) -> None:
    new_client_id = str(uuid.uuid4())
    fakes.bookings_controller.bookings["book-1"] = make_booking_details("book-1")
    fakes.users_client.users_by_email_role[("client@x.com", "client")] = {"id": new_client_id}

    response = await client.post(
        "/bookings/book-1/reassign-client",
        json={"new_client_email": "Client@X.com"},
        headers=admin_headers,
    )

    assert response.status_code == 202
    assert len(fakes.publisher.published) == 1
    event = fakes.publisher.published[0]
    assert event["source"] == "admin"
    assert event["event_type"] == "booking.client_reassigned"
    assert event["data"] == {
        "booking_uid": "book-1",
        "new_client_user_id": new_client_id,
        "requested_by": "admin@test.local",
    }


async def test_reassign_publish_failure_maps_to_502(client, admin_headers, fakes) -> None:
    fakes.bookings_controller.bookings["book-1"] = make_booking_details("book-1")
    fakes.users_client.users_by_email_role[("client@x.com", "client")] = {"id": str(uuid.uuid4())}
    fakes.publisher.error = EventPublishError(
        event_type="booking.client_reassigned",
        source="admin",
        upstream_status=None,
        detail="unreachable",
    )

    response = await client.post(
        "/bookings/book-1/reassign-client",
        json={"new_client_email": "client@x.com"},
        headers=admin_headers,
    )

    assert response.status_code == 502
