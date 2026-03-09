from typing import Annotated

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Query

from event_admin.dto.bookings import BookingListFiltersDto
from event_admin.interfaces.bookings import IBookingsController
from event_admin.schemas.bookings import BookingListItemResponse


root_router = APIRouter(route_class=DishkaRoute)
logger = structlog.get_logger(__name__)


@root_router.get("/health")
async def health() -> dict[str, str]:
    logger.debug("Health check requested")
    return {"status": "ok"}


@root_router.get("/bookings", response_model=list[BookingListItemResponse])
async def list_bookings(
    booking_uids: Annotated[list[str] | None, Query()] = None,
    current_statuses: Annotated[list[str] | None, Query()] = None,
    current_organizer_participant_ref_ids: Annotated[list[int] | None, Query()] = None,
    current_client_participant_ref_ids: Annotated[list[int] | None, Query()] = None,
    controller: FromDishka[IBookingsController] = None,
) -> list[BookingListItemResponse]:
    filters_dto = BookingListFiltersDto(
        booking_uids=booking_uids or [],
        current_statuses=current_statuses or [],
        current_organizer_participant_ref_ids=current_organizer_participant_ref_ids or [],
        current_client_participant_ref_ids=current_client_participant_ref_ids or [],
    )
    booking_dtos = await controller.list_bookings(filters_dto)
    return [BookingListItemResponse.from_dto(dto) for dto in booking_dtos]
