import uuid
from typing import Annotated

import httpx
import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, EmailStr

from event_admin.auth import TokenPayload, create_access_token, require_admin
from event_admin.config import Settings
from event_admin.dto.bookings import BookingListFiltersDto
from event_admin.enums import BookingStatus
from event_admin.interfaces.admin_users import IAdminUsersDBAdapter
from event_admin.interfaces.bookings import IBookingsController
from event_admin.interfaces.event_publisher import IEventPublisher
from event_admin.interfaces.password import IPasswordService
from event_admin.interfaces.totp import ITOTPService
from event_admin.interfaces.users import IUsersClient
from event_admin.schemas.auth import LoginRequest, LoginResponse
from event_admin.schemas.bookings import (
    BookingDetailsResponse,
    BookingFutureBouncedEmailItemResponse,
    BookingListItemResponse,
)
from event_admin.services.users_cache import UsersCache


class ChangeEmailRequest(BaseModel):
    new_email: EmailStr


class ReassignClientRequest(BaseModel):
    new_client_email: EmailStr


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
    settings: FromDishka[Settings],
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
    token = create_access_token(settings, email=user["email"], role=user["role"])
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


@bookings_router.post(
    "/{booking_uid}/reassign-client",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Reassign booking client",
    description="Change the client assigned to a booking to an existing user with the given email.",
)
async def reassign_booking_client(
    booking_uid: str,
    body: ReassignClientRequest,
    client: FromDishka[IUsersClient],
    publisher: FromDishka[IEventPublisher],
    user: Annotated[TokenPayload, Depends(require_admin)],
) -> dict[str, str]:
    new_client = await client.get_user_by_email_role(str(body.new_client_email).lower(), "client")
    if new_client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client with this email not found",
        )

    await publisher.publish(
        source="admin",
        event_type="booking.client_reassigned",
        data={
            "booking_uid": booking_uid,
            "new_client_user_id": new_client["id"],
            "requested_by": user.sub,
        },
    )

    return {"status": "accepted"}


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


@users_router.post(
    "/by-ids",
    summary="Get users by IDs",
    description="Proxy to event-users service. Batch fetch users by a list of UUIDs.",
)
async def proxy_get_users_by_ids(
    body: dict,
    client: FromDishka[IUsersClient],
) -> dict:
    ids_raw = body.get("ids", [])
    if len(ids_raw) > 200:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Maximum 200 IDs per request",
        )
    try:
        user_ids = [uuid.UUID(str(uid)) for uid in ids_raw]
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid UUID in ids") from exc
    try:
        return await client.get_users_by_ids(user_ids)
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


@users_router.post(
    "/id/{user_id}/change-email",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request client email change",
    description="Pre-validates uniqueness, then publishes email change event via RabbitMQ.",
)
async def change_user_email(
    user_id: uuid.UUID,
    body: ChangeEmailRequest,
    client: FromDishka[IUsersClient],
    publisher: FromDishka[IEventPublisher],
    user: Annotated[TokenPayload, Depends(require_admin)],
) -> dict[str, str]:
    try:
        current_user = await client.get_user(user_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found") from exc
        raise HTTPException(status_code=exc.response.status_code) from exc

    if current_user.get("role") != "client":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only client emails can be changed",
        )

    old_email = current_user["email"]
    if old_email.lower() == str(body.new_email).lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New email is the same as current email",
        )

    existing = await client.get_user_by_email_role(str(body.new_email).lower(), "client")
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already in use by another client",
        )

    await publisher.publish(
        source="admin",
        event_type="user.email.change_requested",
        data={
            "user_id": str(user_id),
            "old_email": old_email,
            "new_email": body.new_email,
            "requested_by": user.sub,
        },
    )

    return {"status": "accepted"}


@users_router.get(
    "/id/{user_id}/email-changelog",
    summary="Get email change history",
    description="Proxy to event-users service. Returns email change audit log.",
)
async def get_email_changelog(
    user_id: uuid.UUID,
    client: FromDishka[IUsersClient],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    try:
        return await client.get_email_changelog(user_id, limit=limit, offset=offset)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code) from exc


cache_router = APIRouter(route_class=DishkaRoute)


@cache_router.post(
    "/api/users/cache/invalidate",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Invalidate users cache",
    description="Called by event-users service when users are created or updated. "
    "Authenticated via CACHE_INVALIDATION_TOKEN bearer token.",
)
async def invalidate_users_cache(
    request: Request,
    cache: FromDishka[UsersCache],
    settings: FromDishka[Settings],
) -> None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != settings.cache_invalidation_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid invalidation token")
    cache.invalidate()


root_router.include_router(bookings_router)
root_router.include_router(users_router)
root_router.include_router(cache_router)
