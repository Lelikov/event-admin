"""Shared fixtures: the app is built with a fake DI provider (no real DB / network)."""

import datetime as dt
import uuid
from typing import Any

import httpx
import pytest
from dishka import Provider, Scope, provide
from httpx import ASGITransport, AsyncClient

from event_admin.auth import create_access_token
from event_admin.config import Settings
from event_admin.dto.bookings import (
    BookingDetailsDto,
    BookingFutureBouncedEmailItemDto,
    BookingListFiltersDto,
    BookingListItemDto,
    ParticipantDto,
)
from event_admin.interfaces.admin_users import IAdminUsersDBAdapter
from event_admin.interfaces.bookings import IBookingsController
from event_admin.interfaces.event_publisher import IEventPublisher
from event_admin.interfaces.password import IPasswordService
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
        "event_receiver_url": "http://receiver.test",
        "event_receiver_api_key": "receiver-key-0123456789abcdef",
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def make_booking_details(booking_uid: str = "book-1") -> BookingDetailsDto:
    return BookingDetailsDto(
        id=1,
        booking_uid=booking_uid,
        first_seen_at=NOW,
        last_seen_at=NOW,
        start_time=NOW,
        end_time=NOW,
        current_status="created",
        created_at=NOW,
        updated_at=NOW,
        current_organizer_participant=ParticipantDto(user_id=uuid.uuid4()),
        current_client_participant=ParticipantDto(user_id=uuid.uuid4()),
        organizer_history=(),
        meeting_links=(),
        email_notifications=(),
        telegram_notifications=(),
        chat_events=(),
        video_events=(),
        lifecycle_events=(),
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


class FakeEventPublisher:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []
        self.error: Exception | None = None

    async def publish(self, *, source: str, event_type: str, data: dict[str, Any]) -> None:
        if self.error is not None:
            raise self.error
        self.published.append({"source": source, "event_type": event_type, "data": data})


class Fakes:
    def __init__(self) -> None:
        self.admin_db = FakeAdminUsersDB()
        self.password_service = FakePasswordService()
        self.totp_service = FakeTOTPService()
        self.bookings_controller = FakeBookingsController()
        self.users_client = FakeUsersClient()
        self.publisher = FakeEventPublisher()
        self.users_cache = UsersCache(ttl_seconds=300)
        self.login_guard = LoginGuard(max_failures=5, lockout_seconds=300)


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
    def provide_users_client(self) -> IUsersClient:
        return self._fakes.users_client

    @provide(scope=Scope.APP)
    def provide_event_publisher(self) -> IEventPublisher:
        return self._fakes.publisher

    @provide(scope=Scope.APP)
    def provide_users_cache(self) -> UsersCache:
        return self._fakes.users_cache

    @provide(scope=Scope.APP)
    def provide_login_guard(self) -> LoginGuard:
        return self._fakes.login_guard


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
