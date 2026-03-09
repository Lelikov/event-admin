from __future__ import annotations
from typing import TYPE_CHECKING, Protocol


if TYPE_CHECKING:
    from event_admin.dto.bookings import BookingListFiltersDto, BookingListItemDto


class IBookingsDBAdapter(Protocol):
    async def list_bookings(self, filters: BookingListFiltersDto) -> list[BookingListItemDto]: ...


class IBookingsController(Protocol):
    async def list_bookings(self, filters: BookingListFiltersDto) -> list[BookingListItemDto]: ...
