"""Shared fixtures: the app is built with a fake DI provider (no real DB / network)."""

import os


os.environ.setdefault("OTEL_SDK_DISABLED", "true")

import dataclasses
import datetime as dt
import uuid
from typing import Any, Self

import httpx
import pytest
from dishka import Provider, Scope, provide
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from event_admin.auth import create_access_token
from event_admin.config import Settings
from event_admin.dto.blacklist import (
    UNSET,
    BlacklistCreateDto,
    BlacklistEntryDto,
    BlacklistListFiltersDto,
    BlacklistUpdateDto,
)
from event_admin.dto.bookings import (
    BookingDetailsDto,
    BookingFutureBouncedEmailItemDto,
    BookingListFiltersDto,
    BookingListItemDto,
    BookingMeetingLinkItemDto,
    ParticipantDto,
)
from event_admin.interfaces.admin_users import IAdminUsersDBAdapter
from event_admin.interfaces.blacklist import IBlacklistDBAdapter
from event_admin.interfaces.bookings import IBookingsController
from event_admin.interfaces.event_publisher import IEventPublisher
from event_admin.interfaces.notifier import INotifierClient
from event_admin.interfaces.password import IPasswordService
from event_admin.interfaces.shortener import IShortenerClient
from event_admin.interfaces.totp import ITOTPService
from event_admin.interfaces.users import IUsersClient
from event_admin.main import create_app
from event_admin.services.login_guard import LoginGuard
from event_admin.services.users_cache import UsersCache


NOW = dt.datetime(2026, 6, 11, 12, 0, tzinfo=dt.UTC)


def make_settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = {
        "postgres_dsn": "postgresql+asyncpg://test:test@localhost:5432/test",
        "jwt_secret_key": "unit-test-secret-key-0123456789abcdef",
        "users_service_url": "http://users.test",
        "users_service_api_token": "users-token-0123456789abcdef",
        "cache_invalidation_token": "cache-token-0123456789abcdef",
        "blacklist_service_token": "blacklist-token-0123456789abcdef",
        "event_receiver_url": "http://receiver.test",
        "event_receiver_api_key": "receiver-key-0123456789abcdef",
        "notifier_service_url": "http://notifier.test",
        "notifier_admin_token": "notifier-admin-token-0123456789abcdef",
        "shortener_url": "http://shortener.test",
        "shortener_api_key": "shortener-key-0123456789abcdef",
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


_UNSET: object = object()


def make_booking_details(
    booking_uid: str = "book-1",
    *,
    start_time: dt.datetime | None = NOW,
    end_time: dt.datetime | None = NOW,
    current_status: str | None = "created",
    has_client: bool = True,
    client_user_id: object = _UNSET,
    meeting_links: tuple[BookingMeetingLinkItemDto, ...] = (),
) -> BookingDetailsDto:
    client_participant = None
    if has_client:
        resolved = uuid.uuid4() if client_user_id is _UNSET else client_user_id
        client_participant = ParticipantDto(user_id=resolved)  # type: ignore[arg-type]
    return BookingDetailsDto(
        id=1,
        booking_uid=booking_uid,
        first_seen_at=NOW,
        last_seen_at=NOW,
        start_time=start_time,
        end_time=end_time,
        current_status=current_status,
        created_at=NOW,
        updated_at=NOW,
        current_organizer_participant=ParticipantDto(user_id=uuid.uuid4()),
        current_client_participant=client_participant,
        organizer_history=(),
        meeting_links=meeting_links,
        email_notifications=(),
        telegram_notifications=(),
        chat_events=(),
        video_events=(),
        lifecycle_events=(),
    )


def make_meeting_link(*, user_id: uuid.UUID, meeting_url: str) -> BookingMeetingLinkItemDto:
    return BookingMeetingLinkItemDto(
        id=1,
        participant=ParticipantDto(user_id=user_id),
        meeting_url=meeting_url,
        source_event_id=None,
        occurred_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeAdminUsersDB:
    def __init__(self) -> None:
        self.users: dict[str, dict[str, Any]] = {}

    def add_user(
        self,
        email: str,
        *,
        password: str = "correct-password",
        totp_secret: str = "JBSWY3DPEHPK3PXP",
        role: str = "admin",
        is_active: bool = True,
    ) -> None:
        self.users[email] = {
            "id": uuid.uuid4(),
            "email": email,
            "hashed_password": f"hashed:{password}",
            "totp_secret": totp_secret,
            "role": role,
            "is_active": is_active,
        }

    async def get_by_email(self, email: str) -> dict[str, Any] | None:
        return self.users.get(email)


class FakePasswordService:
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, plain: str, hashed: str) -> bool:
        return hashed == f"hashed:{plain}"


class FakeTOTPService:
    valid_code = "123456"

    def verify(self, code: str, secret: str) -> bool:
        return code == self.valid_code and bool(secret)

    def generate_secret(self) -> str:
        return "JBSWY3DPEHPK3PXP"


class FakeBookingsController:
    def __init__(self) -> None:
        self.bookings: dict[str, BookingDetailsDto] = {}

    async def list_bookings(
        self,
        filters: BookingListFiltersDto,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BookingListItemDto]:
        return []

    async def get_booking_details(self, booking_uid: str) -> BookingDetailsDto | None:
        return self.bookings.get(booking_uid)

    async def list_future_email_bounced_bookings(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BookingFutureBouncedEmailItemDto]:
        return []


class FakeUsersClient:
    def __init__(self) -> None:
        self.users_by_id: dict[uuid.UUID, dict[str, Any]] = {}
        self.users_by_email_role: dict[tuple[str, str], dict[str, Any]] = {}
        self.list_response: dict[str, Any] = {"items": [], "total": 0, "limit": 50, "offset": 0}
        self.changelog_response: dict[str, Any] = {"items": [], "total": 0}

    async def get_user(self, user_id: uuid.UUID) -> dict[str, Any]:
        user = self.users_by_id.get(user_id)
        if user is None:
            request = httpx.Request("GET", f"http://users.test/api/users/id/{user_id}")
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("not found", request=request, response=response)
        return user

    async def get_users_by_ids(self, user_ids: list[uuid.UUID]) -> dict[str, Any]:
        return {"items": [self.users_by_id[uid] for uid in user_ids if uid in self.users_by_id]}

    async def list_users(
        self,
        *,
        email: str | None,
        role: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        return self.list_response

    async def get_user_by_email_role(self, email: str, role: str) -> dict[str, Any] | None:
        return self.users_by_email_role.get((email, role))

    async def get_email_changelog(self, user_id: uuid.UUID, *, limit: int, offset: int) -> dict[str, Any]:
        return self.changelog_response


class FakeBlacklistDB:
    """In-memory IBlacklistDBAdapter mirroring the SQL effectiveness semantics."""

    def __init__(self) -> None:
        self.entries: dict[uuid.UUID, BlacklistEntryDto] = {}
        self.now: dt.datetime = NOW

    def _is_effective(self, entry: BlacklistEntryDto) -> bool:
        if not entry.is_active:
            return False
        if entry.active_from is not None and entry.active_from > self.now:
            return False
        return not (entry.active_until is not None and entry.active_until < self.now)

    async def list_entries(
        self,
        filters: BlacklistListFiltersDto,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[BlacklistEntryDto], int]:
        entries = sorted(self.entries.values(), key=lambda e: e.created_at, reverse=True)
        if filters.field is not None:
            entries = [e for e in entries if e.field == filters.field]
        if filters.value_contains is not None:
            entries = [e for e in entries if filters.value_contains.lower() in e.value.lower()]
        if filters.only_effective:
            entries = [e for e in entries if self._is_effective(e)]
        return entries[offset : offset + limit], len(entries)

    async def get_entry(self, entry_id: uuid.UUID) -> BlacklistEntryDto | None:
        return self.entries.get(entry_id)

    async def create_entry(self, data: BlacklistCreateDto) -> BlacklistEntryDto:
        entry = BlacklistEntryDto(
            id=uuid.uuid4(),
            field=data.field,
            value=data.value,
            is_active=data.is_active,
            active_from=data.active_from,
            active_until=data.active_until,
            comment=data.comment,
            created_by=data.created_by,
            created_at=self.now,
            updated_at=self.now,
        )
        self.entries[entry.id] = entry
        return entry

    async def update_entry(self, entry_id: uuid.UUID, data: BlacklistUpdateDto) -> BlacklistEntryDto | None:
        existing = self.entries.get(entry_id)
        if existing is None:
            return None
        updates = {
            name: getattr(data, name)
            for name in ("field", "value", "is_active", "active_from", "active_until", "comment")
            if getattr(data, name) is not UNSET
        }
        updated = dataclasses.replace(existing, **updates, updated_at=self.now)
        self.entries[entry_id] = updated
        return updated

    async def delete_entry(self, entry_id: uuid.UUID) -> bool:
        return self.entries.pop(entry_id, None) is not None

    async def list_active_values(self, field: str) -> list[str]:
        return [e.value for e in self.entries.values() if e.field == field and self._is_effective(e)]


class FakeEventPublisher:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []
        self.error: Exception | None = None

    async def publish(self, *, source: str, event_type: str, data: dict[str, Any]) -> None:
        if self.error is not None:
            raise self.error
        self.published.append({"source": source, "event_type": event_type, "data": data})


class FakeNotifierClient:
    def __init__(self) -> None:
        self.config_response: dict[str, Any] = {"bindings": []}
        self.put_response: dict[str, Any] = {"status": "ok"}
        self.put_calls: list[tuple[str, str, str]] = []
        self.templates_response: dict[str, Any] = {"templates": []}
        self.preview_response: dict[str, Any] = {"rendered": "preview text"}
        self.error: httpx.HTTPStatusError | None = None

    async def get_config(self) -> dict[str, Any]:
        if self.error is not None:
            raise self.error
        return self.config_response

    async def put_config(
        self, trigger_event: str, recipient_role: str, channel: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        if self.error is not None:
            raise self.error
        self.put_calls.append((trigger_event, recipient_role, channel))
        return self.put_response

    async def unisender_templates(self, *, refresh: bool) -> dict[str, Any]:
        if self.error is not None:
            raise self.error
        return self.templates_response

    async def telegram_preview(self, body: dict[str, Any]) -> dict[str, Any]:
        if self.error is not None:
            raise self.error
        return self.preview_response


class FakeShortenerClient:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def get_click_count(self, ident: str) -> int | None:
        return self.counts.get(ident)


class Fakes:
    def __init__(self) -> None:
        self.admin_db = FakeAdminUsersDB()
        self.password_service = FakePasswordService()
        self.totp_service = FakeTOTPService()
        self.bookings_controller = FakeBookingsController()
        self.blacklist_db = FakeBlacklistDB()
        self.users_client = FakeUsersClient()
        self.publisher = FakeEventPublisher()
        self.notifier_client = FakeNotifierClient()
        self.shortener = FakeShortenerClient()
        self.users_cache = UsersCache(ttl_seconds=300)
        self.login_guard = LoginGuard(max_failures=5, lockout_seconds=300)
        self.engine = FakeEngine()


class FakeConnection:
    """AsyncConnection stand-in for the /ready database ping."""

    def __init__(self, error: Exception | None = None) -> None:
        self._error = error

    async def __aenter__(self) -> Self:
        if self._error is not None:
            raise self._error
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def execute(self, statement: object) -> None:
        return None


class FakeEngine:
    """AsyncEngine stand-in; set `connect_error` to simulate an unreachable database."""

    def __init__(self) -> None:
        self.connect_error: Exception | None = None

    def connect(self) -> FakeConnection:
        return FakeConnection(self.connect_error)


class FakeProvider(Provider):
    """APP-scoped fakes for every dependency the routes resolve."""

    def __init__(self, settings: Settings, fakes: Fakes) -> None:
        super().__init__()
        self._settings = settings
        self._fakes = fakes

    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        return self._settings

    @provide(scope=Scope.APP)
    def provide_admin_users_db(self) -> IAdminUsersDBAdapter:
        return self._fakes.admin_db

    @provide(scope=Scope.APP)
    def provide_password_service(self) -> IPasswordService:
        return self._fakes.password_service

    @provide(scope=Scope.APP)
    def provide_totp_service(self) -> ITOTPService:
        return self._fakes.totp_service

    @provide(scope=Scope.APP)
    def provide_bookings_controller(self) -> IBookingsController:
        return self._fakes.bookings_controller

    @provide(scope=Scope.APP)
    def provide_blacklist_db(self) -> IBlacklistDBAdapter:
        return self._fakes.blacklist_db

    @provide(scope=Scope.APP)
    def provide_users_client(self) -> IUsersClient:
        return self._fakes.users_client

    @provide(scope=Scope.APP)
    def provide_event_publisher(self) -> IEventPublisher:
        return self._fakes.publisher

    @provide(scope=Scope.APP)
    def provide_notifier_client(self) -> INotifierClient:
        return self._fakes.notifier_client

    @provide(scope=Scope.APP)
    def provide_shortener_client(self) -> IShortenerClient:
        return self._fakes.shortener

    @provide(scope=Scope.APP)
    def provide_users_cache(self) -> UsersCache:
        return self._fakes.users_cache

    @provide(scope=Scope.APP)
    def provide_login_guard(self) -> LoginGuard:
        return self._fakes.login_guard

    @provide(scope=Scope.APP)
    def provide_engine(self) -> AsyncEngine:
        return self._fakes.engine  # type: ignore[return-value]


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def fakes() -> Fakes:
    return Fakes()


@pytest.fixture
def app(settings, fakes) -> Any:
    return create_app(settings, provider=FakeProvider(settings, fakes))


@pytest.fixture
async def client(app) -> Any:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
def admin_headers(settings) -> dict[str, str]:
    token = create_access_token(settings, email="admin@test.local", role="admin")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_headers(settings) -> dict[str, str]:
    token = create_access_token(settings, email="user@test.local", role="user")
    return {"Authorization": f"Bearer {token}"}
