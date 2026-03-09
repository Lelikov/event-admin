from event_admin.dto.bookings import BookingListFiltersDto, BookingListItemDto
from event_admin.interfaces.bookings import IBookingsController, IBookingsDBAdapter


class BookingsController(IBookingsController):
    def __init__(self, bookings_db_adapter: IBookingsDBAdapter) -> None:
        self.bookings_db_adapter = bookings_db_adapter

    async def list_bookings(self, filters: BookingListFiltersDto) -> list[BookingListItemDto]:
        return await self.bookings_db_adapter.list_bookings(filters)
