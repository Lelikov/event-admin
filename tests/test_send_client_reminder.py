"""POST /bookings/{uid}/send-client-reminder: resolve current email, gate, publish."""

import uuid
from datetime import UTC, datetime, timedelta

from event_admin.errors import EventPublishError
from tests.conftest import make_booking_details, make_meeting_link


FUTURE = datetime.now(UTC) + timedelta(days=1)
PAST = datetime.now(UTC) - timedelta(days=1)


def _client_user(email: str = "current@example.com") -> dict:
    return {"id": str(uuid.uuid4()), "email": email, "name": "Иван", "role": "client", "time_zone": "Europe/Moscow"}


async def test_unknown_booking_returns_404_and_publishes_nothing(client, admin_headers, fakes) -> None:
    response = await client.post("/bookings/ghost/send-client-reminder", headers=admin_headers)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "booking_not_found"
    assert fakes.publisher.published == []


async def test_no_client_participant_returns_409(client, admin_headers, fakes) -> None:
    fakes.bookings_controller.bookings["b1"] = make_booking_details("b1", has_client=False, start_time=FUTURE)
    response = await client.post("/bookings/b1/send-client-reminder", headers=admin_headers)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "no_client_on_booking"
    assert fakes.publisher.published == []


async def test_past_booking_not_eligible(client, admin_headers, fakes) -> None:
    fakes.bookings_controller.bookings["b1"] = make_booking_details("b1", start_time=PAST)
    response = await client.post("/bookings/b1/send-client-reminder", headers=admin_headers)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "booking_not_eligible"
    assert fakes.publisher.published == []


async def test_cancelled_booking_not_eligible(client, admin_headers, fakes) -> None:
    fakes.bookings_controller.bookings["b1"] = make_booking_details("b1", start_time=FUTURE, current_status="cancelled")
    response = await client.post("/bookings/b1/send-client-reminder", headers=admin_headers)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "booking_not_eligible"
    assert fakes.publisher.published == []


async def test_client_without_account_is_blocked(client, admin_headers, fakes) -> None:
    fakes.bookings_controller.bookings["b1"] = make_booking_details("b1", start_time=FUTURE, client_user_id=None)
    response = await client.post("/bookings/b1/send-client-reminder", headers=admin_headers)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "client_has_no_account"
    assert fakes.publisher.published == []


async def test_client_not_found_in_users_returns_409(client, admin_headers, fakes) -> None:
    cid = uuid.uuid4()
    fakes.bookings_controller.bookings["b1"] = make_booking_details("b1", start_time=FUTURE, client_user_id=cid)
    response = await client.post("/bookings/b1/send-client-reminder", headers=admin_headers)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "client_not_found"
    assert fakes.publisher.published == []


async def test_success_publishes_reminder_with_current_email(client, admin_headers, fakes) -> None:
    cid = uuid.uuid4()
    link = make_meeting_link(user_id=cid, meeting_url="https://meet/abc")
    fakes.bookings_controller.bookings["b1"] = make_booking_details(
        "b1", start_time=FUTURE, end_time=FUTURE, client_user_id=cid, meeting_links=(link,)
    )
    fakes.users_client.users_by_id[cid] = _client_user("current@example.com")

    response = await client.post("/bookings/b1/send-client-reminder", headers=admin_headers)

    assert response.status_code == 202
    assert response.json() == {"status": "accepted", "email": "current@example.com"}
    assert len(fakes.publisher.published) == 1
    event = fakes.publisher.published[0]
    assert event["source"] == "admin"
    assert event["event_type"] == "notification.send_requested"
    data = event["data"]
    assert data["booking_id"] == "b1"
    assert data["trigger_event"] == "BOOKING_REMINDER"
    assert data["recipients"] == [{"email": "current@example.com", "role": "client", "locale": None}]
    td = data["template_data"]
    assert td["client_email"] == "current@example.com"
    assert td["client_name"] == "Иван"
    assert td["meeting_url"] == "https://meet/abc"
    assert "requested_at" in td
    assert td["booking_uid"] == "b1"


async def test_publish_failure_maps_to_502(client, admin_headers, fakes) -> None:
    cid = uuid.uuid4()
    fakes.bookings_controller.bookings["b1"] = make_booking_details("b1", start_time=FUTURE, client_user_id=cid)
    fakes.users_client.users_by_id[cid] = _client_user()
    fakes.publisher.error = EventPublishError(
        event_type="notification.send_requested", source="admin", upstream_status=None, detail="unreachable"
    )
    response = await client.post("/bookings/b1/send-client-reminder", headers=admin_headers)
    assert response.status_code == 502
