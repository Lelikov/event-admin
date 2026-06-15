import hmac
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import httpx
import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from event_admin import metrics
from event_admin.auth import TokenPayload, create_access_token, require_admin
from event_admin.config import Settings
from event_admin.dto.blacklist import BlacklistCreateDto, BlacklistListFiltersDto, BlacklistUpdateDto
from event_admin.dto.bookings import BookingListFiltersDto
from event_admin.enums import BookingStatus
from event_admin.errors import http_error
from event_admin.interfaces.admin_users import IAdminUsersDBAdapter
from event_admin.interfaces.blacklist import IBlacklistDBAdapter
from event_admin.interfaces.bookings import IBookingsController
from event_admin.interfaces.event_publisher import IEventPublisher
from event_admin.interfaces.notifier import INotifierClient
from event_admin.interfaces.password import IPasswordService
from event_admin.interfaces.totp import ITOTPService
from event_admin.interfaces.users import IUsersClient
from event_admin.schemas.auth import LoginRequest, LoginResponse
from event_admin.schemas.blacklist import (
    BlacklistActiveResponse,
    BlacklistCreateRequest,
    BlacklistEntryResponse,
    BlacklistListResponse,
    BlacklistUpdateRequest,
)
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


def _notifier_proxy_error(exc: httpx.HTTPStatusError) -> HTTPException:
    """Map an upstream event-notifier error to a structured response, preserving the status code."""
    upstream_status = exc.response.status_code
    message = f"Notifier service returned an error (status {upstream_status})"
    return http_error(upstream_status, "notifier_service_error", message)


_REMINDER_INELIGIBLE_STATUSES = frozenset({"cancelled", "completed", "no_show"})


def _reminder_eligible(details: Any) -> bool:
    """Return True only for a future booking that is not cancelled/finished."""
    if details.start_time is None or details.start_time <= datetime.now(UTC):
        return False
    return details.current_status not in _REMINDER_INELIGIBLE_STATUSES


def _client_meeting_url(details: Any, client_user_id: uuid.UUID) -> str:
    """Return the client's meeting link if present, else the most recent link, else empty string."""
    links = details.meeting_links
    if not links:
        return ""
    for link in links:
        if link.participant.user_id == client_user_id:
            return link.meeting_url
    return max(links, key=lambda link: link.created_at).meeting_url


def _build_reminder_payload(details: Any, client_user: dict[str, Any]) -> dict[str, Any]:
    email = client_user["email"]
    client_user_id = details.current_client_participant.user_id
    return {
        "booking_id": details.booking_uid,
        "trigger_event": "BOOKING_REMINDER",
        "recipients": [{"email": email, "role": "client", "locale": None}],
        "template_data": {
            "booking_uid": details.booking_uid,
            "start_time": details.start_time.isoformat() if details.start_time else None,
            "end_time": details.end_time.isoformat() if details.end_time else None,
            "client_name": client_user.get("name") or "",
            "client_email": email,
            "meeting_url": _client_meeting_url(details, client_user_id),
            "requested_at": datetime.now(UTC).isoformat(),
        },
    }


# Public routes (no auth required)
root_router = APIRouter(route_class=DishkaRoute)

# Bookings routes (auth enforced by JWTAuthMiddleware + admin RBAC)
bookings_router = APIRouter(prefix="/bookings", route_class=DishkaRoute, dependencies=[Depends(require_admin)])


READY_CHECK_QUERY = "select 1"


@root_router.get("/health", summary="Liveness probe", description="Process is up; no dependency calls.")
async def health() -> dict[str, str]:
    logger.debug("Health check requested")
    return {"status": "ok"}


@root_router.get("/metrics", summary="Prometheus metrics", description="Prometheus exposition endpoint.")
async def metrics_endpoint() -> Response:
    return metrics.metrics_response()


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
        metrics.LOGINS_TOTAL.labels(outcome="blocked").inc()
        logger.warning("login_blocked", email=email, client_ip=client_ip, reason="too_many_failures")
        raise http_error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too_many_login_attempts",
            "Too many failed login attempts; try again later",
        )

    def reject(reason: str) -> HTTPException:
        guard.record_failure(guard_key)
        metrics.LOGINS_TOTAL.labels(outcome="failure").inc()
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
    metrics.LOGINS_TOTAL.labels(outcome="success").inc()
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


@bookings_router.post(
    "/{booking_uid}/send-client-reminder",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send the client a meeting reminder",
    description="Resolve the client's CURRENT email from event-users and publish a "
    "BOOKING_REMINDER notification command for the client.",
)
async def send_client_reminder(
    booking_uid: str,
    controller: FromDishka[IBookingsController],
    client: FromDishka[IUsersClient],
    publisher: FromDishka[IEventPublisher],
    user: Annotated[TokenPayload, Depends(require_admin)],
) -> dict[str, str]:
    details = await controller.get_booking_details(booking_uid)
    if details is None:
        raise http_error(
            status.HTTP_404_NOT_FOUND, "booking_not_found", f"Booking with uid={booking_uid!r} not found"
        )

    client_participant = details.current_client_participant
    if client_participant is None:
        raise http_error(status.HTTP_409_CONFLICT, "no_client_on_booking", "Booking has no client participant")

    if not _reminder_eligible(details):
        raise http_error(
            status.HTTP_409_CONFLICT,
            "booking_not_eligible",
            "Reminder can only be sent for a future, active booking",
        )

    if client_participant.user_id is None:
        raise http_error(
            status.HTTP_409_CONFLICT,
            "client_has_no_account",
            "Client has no linked account; current email cannot be resolved",
        )

    try:
        client_user = await client.get_user(client_participant.user_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise http_error(status.HTTP_409_CONFLICT, "client_not_found", "Client account not found") from exc
        raise _users_proxy_error(exc) from exc

    payload = _build_reminder_payload(details, client_user)
    await publisher.publish(source="admin", event_type="notification.send_requested", data=payload)
    email = client_user["email"]
    logger.info("client_reminder_sent", booking_uid=booking_uid, email=email, requested_by=user.sub)
    return {"status": "accepted", "email": email}


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


# Blacklist routes (admin JWT via middleware + admin RBAC).
# Writing blacklist_entries is a sanctioned exception to the read-only rule (same as admin_users).
blacklist_router = APIRouter(prefix="/api/blacklist", route_class=DishkaRoute, dependencies=[Depends(require_admin)])

# Service route for event-booking; authenticated by BLACKLIST_SERVICE_TOKEN, not admin JWT.
blacklist_service_router = APIRouter(route_class=DishkaRoute)


def _normalize_blacklist_value(field: str, value: str) -> str:
    """Normalize a blacklist value: client_email is stored lowercased (exact, case-insensitive match)."""
    stripped = value.strip()
    if not stripped:
        raise http_error(status.HTTP_400_BAD_REQUEST, "invalid_value", "value must not be blank")
    if field == "client_email":
        return stripped.lower()
    return stripped


def _validate_active_window(active_from: object, active_until: object) -> None:
    if active_from is None or active_until is None:
        return
    if active_from > active_until:  # type: ignore[operator]
        raise http_error(
            status.HTTP_400_BAD_REQUEST,
            "invalid_active_window",
            "active_from must not be after active_until",
        )


def _blacklist_not_found(entry_id: uuid.UUID) -> HTTPException:
    return http_error(
        status.HTTP_404_NOT_FOUND,
        "blacklist_entry_not_found",
        f"Blacklist entry {entry_id} not found",
    )


@blacklist_router.get(
    "",
    response_model=BlacklistListResponse,
    summary="List blacklist entries",
    description="List blacklist entries with pagination and optional filters "
    "(field, value substring, only currently-effective).",
)
async def list_blacklist_entries(
    field: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    value: Annotated[str | None, Query(min_length=1, max_length=320, description="Substring match")] = None,
    only_effective: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: FromDishka[IBlacklistDBAdapter] = None,
) -> BlacklistListResponse:
    filters = BlacklistListFiltersDto(field=field, value_contains=value, only_effective=only_effective)
    entries, total = await db.list_entries(filters, limit=limit, offset=offset)
    return BlacklistListResponse(
        items=[BlacklistEntryResponse.from_dto(dto) for dto in entries],
        total=total,
        limit=limit,
        offset=offset,
    )


@blacklist_router.post(
    "",
    response_model=BlacklistEntryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create blacklist entry",
    description="Add a blacklist entry. client_email values are stored lowercased (case-insensitive match).",
)
async def create_blacklist_entry(
    body: BlacklistCreateRequest,
    db: FromDishka[IBlacklistDBAdapter],
    user: Annotated[TokenPayload, Depends(require_admin)],
) -> BlacklistEntryResponse:
    _validate_active_window(body.active_from, body.active_until)
    entry = await db.create_entry(
        BlacklistCreateDto(
            field=body.field,
            value=_normalize_blacklist_value(body.field, body.value),
            is_active=body.is_active,
            active_from=body.active_from,
            active_until=body.active_until,
            comment=body.comment,
            created_by=user.sub,
        ),
    )
    metrics.BLACKLIST_OPS_TOTAL.labels(op="create").inc()
    logger.info("blacklist_entry_created", entry_id=str(entry.id), field=entry.field, created_by=user.sub)
    return BlacklistEntryResponse.from_dto(entry)


@blacklist_router.patch(
    "/{entry_id}",
    response_model=BlacklistEntryResponse,
    summary="Update blacklist entry",
    description="Partially update a blacklist entry; omitted fields are left untouched.",
)
async def update_blacklist_entry(
    entry_id: uuid.UUID,
    body: BlacklistUpdateRequest,
    db: FromDishka[IBlacklistDBAdapter],
    user: Annotated[TokenPayload, Depends(require_admin)],
) -> BlacklistEntryResponse:
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise http_error(status.HTTP_400_BAD_REQUEST, "empty_update", "Provide at least one field to update")
    for name in ("field", "value", "is_active"):
        if name in updates and updates[name] is None:
            raise http_error(status.HTTP_400_BAD_REQUEST, "field_not_nullable", f"{name} cannot be null")

    existing = await db.get_entry(entry_id)
    if existing is None:
        raise _blacklist_not_found(entry_id)

    effective_field = updates.get("field", existing.field)
    if "value" in updates:
        updates["value"] = _normalize_blacklist_value(effective_field, updates["value"])
    if "value" not in updates and effective_field == "client_email":
        # Field switched to client_email: re-normalize the stored value too.
        updates["value"] = _normalize_blacklist_value(effective_field, existing.value)
    _validate_active_window(
        updates.get("active_from", existing.active_from),
        updates.get("active_until", existing.active_until),
    )

    updated = await db.update_entry(entry_id, BlacklistUpdateDto(**updates))
    if updated is None:
        raise _blacklist_not_found(entry_id)
    metrics.BLACKLIST_OPS_TOTAL.labels(op="update").inc()
    logger.info("blacklist_entry_updated", entry_id=str(entry_id), updated_by=user.sub, fields=sorted(updates))
    return BlacklistEntryResponse.from_dto(updated)


@blacklist_router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete blacklist entry",
)
async def delete_blacklist_entry(
    entry_id: uuid.UUID,
    db: FromDishka[IBlacklistDBAdapter],
    user: Annotated[TokenPayload, Depends(require_admin)],
) -> None:
    deleted = await db.delete_entry(entry_id)
    if not deleted:
        raise _blacklist_not_found(entry_id)
    metrics.BLACKLIST_OPS_TOTAL.labels(op="delete").inc()
    logger.info("blacklist_entry_deleted", entry_id=str(entry_id), deleted_by=user.sub)


@blacklist_service_router.get(
    "/api/blacklist/active",
    response_model=BlacklistActiveResponse,
    summary="List currently-effective blacklist values (service endpoint)",
    description="Called by event-booking. Authenticated via BLACKLIST_SERVICE_TOKEN bearer token; "
    "effectiveness (is_active + active window) is evaluated in SQL.",
)
async def list_active_blacklist_values(
    request: Request,
    db: FromDishka[IBlacklistDBAdapter],
    settings: FromDishka[Settings],
    field: Annotated[str, Query(min_length=1, max_length=64)] = "client_email",
) -> BlacklistActiveResponse:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], settings.blacklist_service_token):
        raise http_error(status.HTTP_401_UNAUTHORIZED, "invalid_service_token", "Invalid service token")
    values = await db.list_active_values(field)
    return BlacklistActiveResponse(field=field, values=values)


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


# Notifications routes (proxy to event-notifier admin API)
notifications_router = APIRouter(
    prefix="/api/notifications",
    route_class=DishkaRoute,
    dependencies=[Depends(require_admin)],
)


@notifications_router.get(
    "/config",
    summary="Get notification bindings",
    description="Proxy to event-notifier. Returns all per-event channel bindings.",
)
async def proxy_get_notification_config(client: FromDishka[INotifierClient]) -> dict:
    try:
        return await client.get_config()
    except httpx.HTTPStatusError as exc:
        raise _notifier_proxy_error(exc) from exc


@notifications_router.put(
    "/config/{trigger_event}/{recipient_role}/{channel}",
    summary="Update notification binding",
    description="Proxy to event-notifier. Enable/disable a channel and update its per-role template config.",
)
async def proxy_put_notification_config(
    trigger_event: str,
    recipient_role: str,
    channel: str,
    body: dict,
    client: FromDishka[INotifierClient],
) -> dict:
    try:
        return await client.put_config(trigger_event, recipient_role, channel, body)
    except httpx.HTTPStatusError as exc:
        raise _notifier_proxy_error(exc) from exc


@notifications_router.get(
    "/unisender-templates",
    summary="List UniSender templates",
    description="Proxy to event-notifier. Returns cached UniSender template list.",
)
async def proxy_unisender_templates(
    client: FromDishka[INotifierClient],
    refresh: bool = False,
) -> dict:
    try:
        return await client.unisender_templates(refresh=refresh)
    except httpx.HTTPStatusError as exc:
        raise _notifier_proxy_error(exc) from exc


@notifications_router.post(
    "/telegram/preview",
    summary="Preview Telegram template",
    description="Proxy to event-notifier. Renders a Jinja2 body with sample data.",
)
async def proxy_telegram_preview(body: dict, client: FromDishka[INotifierClient]) -> dict:
    try:
        return await client.telegram_preview(body)
    except httpx.HTTPStatusError as exc:
        raise _notifier_proxy_error(exc) from exc


root_router.include_router(bookings_router)
root_router.include_router(users_router)
root_router.include_router(blacklist_router)
root_router.include_router(blacklist_service_router)
root_router.include_router(cache_router)
root_router.include_router(notifications_router)
