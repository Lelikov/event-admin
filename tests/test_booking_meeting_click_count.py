"""GET /bookings/{uid} enriches meeting links with shortener click counts."""

import uuid

from tests.conftest import make_booking_details, make_meeting_link


async def test_meeting_links_get_click_count(client, admin_headers, fakes) -> None:
    cid = uuid.uuid4()
    link = make_meeting_link(user_id=cid, meeting_url="http://event-shortener:8888/qmk-rba-htz")
    fakes.bookings_controller.bookings["b1"] = make_booking_details("b1", meeting_links=(link,))
    fakes.shortener.counts["qmk-rba-htz"] = 5

    resp = await client.get("/bookings/b1", headers=admin_headers)
    assert resp.status_code == 200
    links = resp.json()["meeting_links"]
    assert len(links) == 1
    assert links[0]["click_count"] == 5


async def test_meeting_link_click_count_null_when_shortener_unknown(client, admin_headers, fakes) -> None:
    cid = uuid.uuid4()
    link = make_meeting_link(user_id=cid, meeting_url="http://event-shortener:8888/zzz-zzz-zzz")
    fakes.bookings_controller.bookings["b1"] = make_booking_details("b1", meeting_links=(link,))

    resp = await client.get("/bookings/b1", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["meeting_links"][0]["click_count"] is None
