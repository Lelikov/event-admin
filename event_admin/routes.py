import hmac
import uuid
from typing import Annotated

import httpx
import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from event_admin.auth import TokenPayload, create_access_token, require_admin
from event_admin.config import Settings
from event_admin.dto.bookings import BookingListFiltersDto
from event_admin.enums import BookingStatus
from event_admin.errors import http_error
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
from event_admin.schemas.users_proxy import (
    ProxiedEmailChangelogResponse,
    ProxiedUser,
    ProxiedUsersByIdsResponse,
    ProxiedUsersListResponse,
    UsersByIdsRequest,
)
from event_admin.services.login_guard import LoginGuard
from event_admin.services.users_cache import UsersCache


class ChangeEmailRequest(BaseModel):
    new_email: EmailStr


class ReassignClientRequest(BaseModel):
    new_client_email: EmailStr


logger = structlog.get_logger(__name__)


def _users_proxy_error(exc: httpx.HTTPStatusError) -> HTTPException:
    """Map an upstream event-users error to a structured response, preserving the status code."""
    upstream_status = exc.response.status_code
    message = f"Users service returned an error (status {upstream_status})"
    return http_error(upstream_status, "users_service_error", message)


# Public routes (no auth required)
root_router = APIRouter(route_class=DishkaRoute)

# Bookings routes (auth enforced by JWTAuthMiddleware + admin RBAC)
bookings_router = APIRouter(prefix="/bookings", route_class=DishkaRoute, dependencies=[Depends(require_admin)])


READY_CHECK_QUERY = "select 1"


@root_router.get("/health", summary="Liveness probe", description="Process is up; no dependency calls.")
async def health() -> dict[str, str]:
    logger.debug("Health check requested")
    return {"status": "ok"}


@root_router.get("/ready", summary="Readiness probe", description="Verifies PostgreSQL connectivity.")
async def ready(engine: FromDishka[AsyncEngine]) -> JSONResponse:
    database_ok = False
    try:
        async with engine.connect() as connection:
            await connection.execute(text(READY_CHECK_QUERY))
        database_ok = True
    except Exception:
        logger.exception("Readiness check failed: database unreachable")

    checks = {"database": database_ok}
    if not database_ok:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "checks": checks},
        )
    return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "ready", "checks": checks})


@root_router.post(
    "/auth/login",
    response_model=LoginResponse,
    summary="Admin login",
    description="Authenticate with email, password, and TOTP code. Returns a JWT access token.",
)
async def login(
    request: Request,
    body: LoginRequest,
    db: FromDishka[IAdminUsersDBAdapter],
    password_service: FromDishka[IPasswordService],
    totp_service: FromDishka[ITOTPService],
    guard: FromDishka[LoginGuard],
    settings: FromDishka[Settings],
) -> LoginResponse:
    email = str(body.email).lower()
    client_ip = request.client.host if request.client else "unknown"
    guard_key = f"{client_ip}:{email}"

    if guard.is_locked(guard_key):
        logger.warning("login_blocked", email=email, client_ip=client_ip, reason="too_many_failures")
        raise http_error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too_many_login_attempts",
            "Too many failed login attempts; try again later",
        )

    def reject(reason: str) -> HTTPException:
        guard.record_failure(guard_key)
        logger.warning("login_failed", email=email, client_ip=client_ip, reason=reason)
        return http_error(status.HTTP_401_UNAUTHORIZED, "invalid_credentials", "Invalid credentials")

    user = await db.get_by_email(body.email)
    if user is None:
        raise reject("user_not_found")
    if not user["is_active"]:
        raise reject("user_inactive")
    if not password_service.verify(body.password, user["hashed_password"]):
        raise reject("bad_password")
    if guard.totp_is_replay(email, body.totp_code):
        raise reject("totp_replay")
    if not totp_service.verify(body.totp_code, user["totp_secret"]):
        raise reject("bad_totp")

    guard.mark_totp_used(email, body.totp_code)
    guard.reset(guard_key)
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
        raise http_error(status.HTTP_400_BAD_REQUEST, "too_many_booking_uids", "Too many booking_uids (max 200)")
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
        raise http_error(
            status.HTTP_404_NOT_FOUND,
            "booking_not_found",
            f"Booking with uid={booking_uid!r} not found",
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
    controller: FromDishka[IBookingsController],
    user: Annotated[TokenPayload, Depends(require_admin)],
) -> dict[str, str]:
    booking = await controller.get_booking_details(booking_uid)
    if booking is None:
        raise http_error(
            status.HTTP_404_NOT_FOUND,
            "booking_not_found",
            f"Booking with uid={booking_uid!r} not found",
        )

    new_client = await client.get_user_by_email_role(str(body.new_client_email).lower(), "client")
    if new_client is None:
        raise http_error(
            status.HTTP_404_NOT_FOUND,
            "client_not_found",
            "Client with this email not found",
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
    response_model=ProxiedUsersListResponse,
    summary="List users",
    description="Proxy to event-users service. List users with optional email/role filters.",
)
async def proxy_list_users(
    client: FromDishka[IUsersClient],
    email: Annotated[str | None, Query()] = None,
    role: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProxiedUsersListResponse:
    try:
        data = await client.list_users(email=email, role=role, limit=limit, offset=offset)
    except httpx.HTTPStatusError as exc:
        raise _users_proxy_error(exc) from exc
    return ProxiedUsersListResponse.model_validate(data)


@users_router.post(
    "/by-ids",
    response_model=ProxiedUsersByIdsResponse,
    summary="Get users by IDs",
    description="Proxy to event-users service. Batch fetch users by a list of UUIDs (max 200).",
)
async def proxy_get_users_by_ids(
    body: UsersByIdsRequest,
    client: FromDishka[IUsersClient],
) -> ProxiedUsersByIdsResponse:
    try:
        data = await client.get_users_by_ids(body.ids)
    except httpx.HTTPStatusError as exc:
        raise _users_proxy_error(exc) from exc
    return ProxiedUsersByIdsResponse.model_validate(data)


@users_router.get(
    "/id/{user_id}",
    response_model=ProxiedUser,
    summary="Get user by ID",
    description="Proxy to event-users service. Get a single user by UUID.",
)
async def proxy_get_user(
    user_id: uuid.UUID,
    client: FromDishka[IUsersClient],
) -> ProxiedUser:
    try:
        data = await client.get_user(user_id)
    except httpx.HTTPStatusError as exc:
        raise _users_proxy_error(exc) from exc
    return ProxiedUser.model_validate(data)


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
            raise http_error(status.HTTP_404_NOT_FOUND, "user_not_found", "User not found") from exc
        raise _users_proxy_error(exc) from exc

    if current_user.get("role") != "client":
        raise http_error(
            status.HTTP_400_BAD_REQUEST,
            "not_a_client",
            "Only client emails can be changed",
        )

    # Normalize once; the same lowercased value is used for the uniqueness
    # check AND the published payload so downstream cannot store a
    # case-variant duplicate of an address the pre-check reported as free.
    new_email = str(body.new_email).lower()

    old_email = current_user["email"]
    if old_email.lower() == new_email:
        raise http_error(
            status.HTTP_400_BAD_REQUEST,
            "email_unchanged",
            "New email is the same as current email",
        )

    existing = await client.get_user_by_email_role(new_email, "client")
    if existing is not None:
        raise http_error(
            status.HTTP_409_CONFLICT,
            "email_already_in_use",
            "Email already in use by another client",
        )

    await publisher.publish(
        source="admin",
        event_type="user.email.change_requested",
        data={
            "user_id": str(user_id),
            "old_email": old_email,
            "new_email": new_email,
            "requested_by": user.sub,
        },
    )

    return {"status": "accepted"}


@users_router.get(
    "/id/{user_id}/email-changelog",
    response_model=ProxiedEmailChangelogResponse,
    summary="Get email change history",
    description="Proxy to event-users service. Returns email change audit log.",
)
async def get_email_changelog(
    user_id: uuid.UUID,
    client: FromDishka[IUsersClient],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProxiedEmailChangelogResponse:
    try:
        data = await client.get_email_changelog(user_id, limit=limit, offset=offset)
    except httpx.HTTPStatusError as exc:
        raise _users_proxy_error(exc) from exc
    return ProxiedEmailChangelogResponse.model_validate(data)


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
    if not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], settings.cache_invalidation_token):
        raise http_error(status.HTTP_401_UNAUTHORIZED, "invalid_invalidation_token", "Invalid invalidation token")
    cache.invalidate()


root_router.include_router(bookings_router)
root_router.include_router(users_router)
root_router.include_router(cache_router)
