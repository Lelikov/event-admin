from typing import Annotated

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Path, Query, status

from event_admin.dto.bookings import BookingListFiltersDto, ParticipantListFiltersDto
from event_admin.interfaces.bookings import IBookingsController
from event_admin.schemas.bookings import (
    BookingDetailsResponse,
    BookingFutureBouncedEmailItemResponse,
    BookingListItemResponse,
    ParticipantListItemResponse,
)


root_router = APIRouter(route_class=DishkaRoute)
logger = structlog.get_logger(__name__)


@root_router.get("/health")
async def health() -> dict[str, str]:
    logger.debug("Health check requested")
    return {"status": "ok"}


@root_router.get("/participants", response_model=list[ParticipantListItemResponse])
async def list_participants(
    roles: Annotated[list[str] | None, Query()] = None,
    email: Annotated[str | None, Query(min_length=1)] = None,
    controller: FromDishka[IBookingsController] = None,
) -> list[ParticipantListItemResponse]:
    filters_dto = ParticipantListFiltersDto(
        roles=tuple(roles or []),
        email=email,
    )
    participant_dtos = await controller.list_participants(filters_dto)
    return [ParticipantListItemResponse.from_dto(dto) for dto in participant_dtos]


@root_router.get("/bookings", response_model=list[BookingListItemResponse])
async def list_bookings(
    booking_uids: Annotated[list[str] | None, Query()] = None,
    current_statuses: Annotated[list[str] | None, Query()] = None,
    current_organizer_participant_ref_ids: Annotated[list[int] | None, Query()] = None,
    current_client_participant_ref_ids: Annotated[list[int] | None, Query()] = None,
    controller: FromDishka[IBookingsController] = None,
) -> list[BookingListItemResponse]:
    filters_dto = BookingListFiltersDto(
        booking_uids=tuple(booking_uids or []),
        current_statuses=tuple(current_statuses or []),
        current_organizer_participant_ref_ids=tuple(current_organizer_participant_ref_ids or []),
        current_client_participant_ref_ids=tuple(current_client_participant_ref_ids or []),
    )
    booking_dtos = await controller.list_bookings(filters_dto)
    return [BookingListItemResponse.from_dto(dto) for dto in booking_dtos]


@root_router.get(
    "/bookings/future-email-bounced",
    response_model=list[BookingFutureBouncedEmailItemResponse],
)
async def list_future_email_bounced_bookings(
    controller: FromDishka[IBookingsController],
) -> list[BookingFutureBouncedEmailItemResponse]:
    booking_dtos = await controller.list_future_email_bounced_bookings()
    return [BookingFutureBouncedEmailItemResponse.from_dto(dto) for dto in booking_dtos]


@root_router.get("/bookings/{booking_uid}", response_model=BookingDetailsResponse)
async def get_booking_details(
    booking_uid: Annotated[str, Path(min_length=1)],
    controller: FromDishka[IBookingsController],
) -> BookingDetailsResponse:
    booking_details_dto = await controller.get_booking_details(booking_uid)
    if booking_details_dto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking with uid={booking_uid!r} not found",
        )
    return BookingDetailsResponse.from_dto(booking_details_dto)
