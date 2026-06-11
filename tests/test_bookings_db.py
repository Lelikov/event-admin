"""BookingsDBAdapter: child queries must never run concurrently on the shared session."""

import asyncio
import datetime as dt
import uuid
from typing import Any

import pytest

from event_admin.adapters.bookings_db import BookingsDBAdapter
from tests.conftest import make_booking_details


NOW = dt.datetime(2026, 6, 11, 12, 0, tzinfo=dt.UTC)

BOOKING_ROW = {
    "id": 1,
    "booking_uid": "book-1",
    "first_seen_at": NOW,
    "last_seen_at": NOW,
    "start_time": NOW,
    "end_time": NOW,
    "current_status": "created",
    "created_at": NOW,
    "updated_at": NOW,
    "current_organizer_user_id": uuid.uuid4(),
    "current_client_user_id": uuid.uuid4(),
}


class ConcurrencyDetectingSqlExecutor:
    """Mimics SQLAlchemy AsyncSession: concurrent operations are an error.

    A reintroduced asyncio.gather() over this executor fails the test the
    same way the real AsyncSession raises InvalidRequestError in production.
    """

    def __init__(self, booking_row: dict[str, Any] | None = BOOKING_ROW) -> None:
        self._booking_row = booking_row
        self._in_flight = False
        self.queries: list[str] = []

    async def _execute(self, query: str) -> None:
        if self._in_flight:
            raise RuntimeError(
                "concurrent operations are not permitted on a single AsyncSession",
            )
        self._in_flight = True
        try:
            self.queries.append(query)
            # Yield control so interleaving (e.g. via asyncio.gather) is observable.
            await asyncio.sleep(0)
        finally:
            self._in_flight = False

    async def fetch_one(self, query: str, values: dict) -> dict[str, Any] | None:
        await self._execute(query)
        return self._booking_row

    async def fetch_all(self, query: str, values: dict) -> list[dict[str, Any]]:
        await self._execute(query)
        return []


async def test_get_booking_details_runs_queries_sequentially() -> None:
    executor = ConcurrencyDetectingSqlExecutor()
    adapter = BookingsDBAdapter(executor)

    details = await adapter.get_booking_details("book-1")

    assert details is not None
    assert details.booking_uid == "book-1"
    # booking row + 7 child-table queries (status history is skipped when
    # there are no email notifications)
    assert len(executor.queries) == 8


async def test_get_booking_details_returns_none_for_unknown_uid() -> None:
    executor = ConcurrencyDetectingSqlExecutor(booking_row=None)
    adapter = BookingsDBAdapter(executor)

    assert await adapter.get_booking_details("missing") is None
    assert len(executor.queries) == 1


async def test_gather_over_shared_executor_is_detected() -> None:
    """Sanity check: the detector actually trips on concurrent use."""
    executor = ConcurrencyDetectingSqlExecutor()
    with pytest.raises(RuntimeError, match="concurrent operations"):
        await asyncio.gather(
            executor.fetch_all("SELECT 1", {}),
            executor.fetch_all("SELECT 2", {}),
        )


async def test_get_booking_details_endpoint_returns_200(client, admin_headers, fakes) -> None:
    fakes.bookings_controller.bookings["book-1"] = make_booking_details("book-1")
    response = await client.get("/bookings/book-1", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["booking_uid"] == "book-1"


async def test_get_booking_details_endpoint_returns_404(client, admin_headers) -> None:
    response = await client.get("/bookings/unknown-uid", headers=admin_headers)
    assert response.status_code == 404
