import uuid
from typing import Annotated

import httpx
import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from event_admin.auth import create_access_token, require_admin
from event_admin.dto.bookings import BookingListFiltersDto
from event_admin.enums import BookingStatus
from event_admin.interfaces.admin_users import IAdminUsersDBAdapter
from event_admin.interfaces.bookings import IBookingsController
from event_admin.interfaces.password import IPasswordService
from event_admin.interfaces.totp import ITOTPService
from event_admin.interfaces.users import IUsersClient
from event_admin.schemas.auth import LoginRequest, LoginResponse
from event_admin.schemas.bookings import (
    BookingDetailsResponse,
    BookingFutureBouncedEmailItemResponse,
    BookingListItemResponse,
)


logger = structlog.get_logger(__name__)

# Public routes (no auth required)
root_router = APIRouter(route_class=DishkaRoute)

# Bookings routes (auth enforced by JWTAuthMiddleware + admin RBAC)
bookings_router = APIRouter(prefix="/bookings", route_class=DishkaRoute, dependencies=[Depends(require_admin)])


@root_router.get("/health", summary="Health check", description="Returns service health status.")
async def health() -> dict[str, str]:
    logger.debug("Health check requested")
    return {"status": "ok"}


@root_router.post(
    "/auth/login",
    response_model=LoginResponse,
    summary="Admin login",
    description="Authenticate with email, password, and TOTP code. Returns a JWT access token.",
)
async def login(
    body: LoginRequest,
    db: FromDishka[IAdminUsersDBAdapter],
    password_service: FromDishka[IPasswordService],
    totp_service: FromDishka[ITOTPService],
) -> LoginResponse:
    user = await db.get_by_email(body.email)
    if user is None:
        logger.warning("login_failed", email=body.email, reason="user_not_found")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user["is_active"]:
        logger.warning("login_failed", email=body.email, reason="user_inactive")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not password_service.verify(body.password, user["hashed_password"]):
        logger.warning("login_failed", email=body.email, reason="bad_password")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not totp_service.verify(body.totp_code, user["totp_secret"]):
        logger.warning("login_failed", email=body.email, reason="bad_totp")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(email=user["email"], role=user["role"])
    logger.info("login_success", email=user["email"], role=user["role"])
    return LoginResponse(access_token=token, role=user["role"])


@root_router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout",
    description="Client-side logout. No server-side token revocation.",
)
async def logout() -> None:
    return None


@bookings_router.get(
    "",
    response_model=list[BookingListItemResponse],
    summary="List bookings",
    description="List bookings with optional filters by UID, status, organizer, or client.",
)
async def list_bookings(
    booking_uids: Annotated[list[str] | None, Query()] = None,
    current_statuses: Annotated[list[BookingStatus] | None, Query()] = None,
    current_organizer_user_ids: Annotated[list[uuid.UUID] | None, Query()] = None,
    current_client_user_ids: Annotated[list[uuid.UUID] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    controller: FromDishka[IBookingsController] = None,
) -> list[BookingListItemResponse]:
    if booking_uids and len(booking_uids) > 200:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Too many booking_uids (max 200)")
    filters_dto = BookingListFiltersDto(
        booking_uids=tuple(booking_uids or []),
        current_statuses=tuple(current_statuses or []),
        current_organizer_user_ids=tuple(current_organizer_user_ids or []),
        current_client_user_ids=tuple(current_client_user_ids or []),
    )
    booking_dtos = await controller.list_bookings(filters_dto, limit=limit, offset=offset)
    return [BookingListItemResponse.from_dto(dto) for dto in booking_dtos]


@bookings_router.get(
    "/future-email-bounced",
    response_model=list[BookingFutureBouncedEmailItemResponse],
    summary="List future email-bounced bookings",
    description="List future bookings that have email bounce notifications.",
)
async def list_future_email_bounced_bookings(
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    controller: FromDishka[IBookingsController] = None,
) -> list[BookingFutureBouncedEmailItemResponse]:
    booking_dtos = await controller.list_future_email_bounced_bookings(limit=limit, offset=offset)
    return [BookingFutureBouncedEmailItemResponse.from_dto(dto) for dto in booking_dtos]


@bookings_router.get(
    "/{booking_uid}",
    response_model=BookingDetailsResponse,
    summary="Get booking details",
    description="Get full booking details including notifications, meeting links, and event history.",
)
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


# Users routes (proxy to event-users service)
users_router = APIRouter(prefix="/api/users", route_class=DishkaRoute, dependencies=[Depends(require_admin)])


@users_router.get(
    "",
    summary="List users",
    description="Proxy to event-users service. List users with optional email/role filters.",
)
async def proxy_list_users(
    client: FromDishka[IUsersClient],
    email: Annotated[str | None, Query()] = None,
    role: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    try:
        return await client.list_users(email=email, role=role, limit=limit, offset=offset)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code) from exc


@users_router.get(
    "/id/{user_id}",
    summary="Get user by ID",
    description="Proxy to event-users service. Get a single user by UUID.",
)
async def proxy_get_user(
    user_id: uuid.UUID,
    client: FromDishka[IUsersClient],
) -> dict:
    try:
        return await client.get_user(user_id)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code) from exc


root_router.include_router(bookings_router)
root_router.include_router(users_router)
