from event_admin.dto.bookings import (
    BookingDetailsDto,
    BookingFutureBouncedEmailItemDto,
    BookingListFiltersDto,
    BookingListItemDto,
)
from event_admin.interfaces.bookings import IBookingsController, IBookingsDBAdapter


class BookingsController(IBookingsController):
    def __init__(self, bookings_db_adapter: IBookingsDBAdapter) -> None:
        self.bookings_db_adapter = bookings_db_adapter

    async def list_bookings(
        self,
        filters: BookingListFiltersDto,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BookingListItemDto]:
        return await self.bookings_db_adapter.list_bookings(filters, limit=limit, offset=offset)

    async def get_booking_details(self, booking_uid: str) -> BookingDetailsDto | None:
        return await self.bookings_db_adapter.get_booking_details(booking_uid)

    async def list_future_email_bounced_bookings(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BookingFutureBouncedEmailItemDto]:
        return await self.bookings_db_adapter.list_future_email_bounced_bookings(limit=limit, offset=offset)
