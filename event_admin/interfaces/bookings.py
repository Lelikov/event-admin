from __future__ import annotations
from typing import TYPE_CHECKING, Protocol


if TYPE_CHECKING:
    from event_admin.dto.bookings import (
        BookingDetailsDto,
        BookingFutureBouncedEmailItemDto,
        BookingListFiltersDto,
        BookingListItemDto,
    )


class IBookingsDBAdapter(Protocol):
    async def list_bookings(
        self,
        filters: BookingListFiltersDto,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BookingListItemDto]: ...

    async def get_booking_details(self, booking_uid: str) -> BookingDetailsDto | None: ...

    async def list_future_email_bounced_bookings(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BookingFutureBouncedEmailItemDto]: ...


class IBookingsController(Protocol):
    async def list_bookings(
        self,
        filters: BookingListFiltersDto,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BookingListItemDto]: ...

    async def get_booking_details(self, booking_uid: str) -> BookingDetailsDto | None: ...

    async def list_future_email_bounced_bookings(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BookingFutureBouncedEmailItemDto]: ...
