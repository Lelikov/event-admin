from collections.abc import AsyncGenerator

import structlog
from dishka import Provider, Scope, provide
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from event_admin.adapters.admin_users_db import AdminUsersDBAdapter
from event_admin.adapters.blacklist_db import BlacklistDBAdapter
from event_admin.adapters.bookings_db import BookingsDBAdapter
from event_admin.adapters.event_publisher import EventPublisherClient
from event_admin.adapters.notifier_client import NotifierClient
from event_admin.adapters.sql import SqlExecutor
from event_admin.adapters.users_client import UsersClient
from event_admin.config import Settings
from event_admin.controllers.bookings import BookingsController
from event_admin.interfaces.admin_users import IAdminUsersDBAdapter
from event_admin.interfaces.blacklist import IBlacklistDBAdapter
from event_admin.interfaces.bookings import IBookingsController, IBookingsDBAdapter
from event_admin.interfaces.event_publisher import IEventPublisher
from event_admin.interfaces.notifier import INotifierClient
from event_admin.interfaces.password import IPasswordService
from event_admin.interfaces.sql import ISqlExecutor, ISqlExecutorFactory
from event_admin.interfaces.totp import ITOTPService
from event_admin.interfaces.users import IUsersClient
from event_admin.services.login_guard import LoginGuard
from event_admin.services.password import PasswordService
from event_admin.services.totp import TOTPService
from event_admin.services.users_cache import UsersCache


logger = structlog.get_logger(__name__)


class AppProvider(Provider):
    """DI provider; receives the single Settings instance from create_app()."""

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings

    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        logger.info(
            "Settings initialized",
            debug=self._settings.debug,
            log_level=self._settings.log_level,
        )
        return self._settings

    @provide(scope=Scope.APP)
    async def provide_db_engine(
        self,
        settings: Settings,
    ) -> AsyncGenerator[AsyncEngine]:
        engine = create_async_engine(
            str(settings.postgres_dsn),
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
        )
        try:
            yield engine
        finally:
            await engine.dispose()

    @provide(scope=Scope.APP)
    def provide_sessionmaker(
        self,
        engine: AsyncEngine,
    ) -> async_sessionmaker[AsyncSession]:
        return async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            autoflush=False,
        )

    @provide(scope=Scope.REQUEST)
    async def provide_session(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
    ) -> AsyncGenerator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    @provide(scope=Scope.REQUEST)
    def provide_sql_executor(self, session: AsyncSession) -> ISqlExecutor:
        return SqlExecutor(session)

    @provide(scope=Scope.APP)
    def provide_password_service(self) -> IPasswordService:
        return PasswordService()

    @provide(scope=Scope.APP)
    def provide_totp_service(self) -> ITOTPService:
        return TOTPService()

    @provide(scope=Scope.APP)
    def provide_login_guard(self, settings: Settings) -> LoginGuard:
        return LoginGuard(
            max_failures=settings.login_max_failures,
            lockout_seconds=settings.login_lockout_seconds,
        )

    @provide(scope=Scope.REQUEST)
    def provide_admin_users_db_adapter(self, sql_executor: ISqlExecutor) -> IAdminUsersDBAdapter:
        return AdminUsersDBAdapter(sql_executor)

    @provide(scope=Scope.REQUEST)
    def provide_blacklist_db_adapter(self, sql_executor: ISqlExecutor) -> IBlacklistDBAdapter:
        return BlacklistDBAdapter(sql_executor)

    @provide(scope=Scope.REQUEST)
    def provide_bookings_db_adapter(self, sql_executor: ISqlExecutor) -> IBookingsDBAdapter:
        return BookingsDBAdapter(sql_executor)

    @provide(scope=Scope.REQUEST)
    def provide_bookings_controller(self, bookings_db_adapter: IBookingsDBAdapter) -> IBookingsController:
        return BookingsController(bookings_db_adapter)

    @provide(scope=Scope.APP)
    def provide_sql_executor_factory(self) -> ISqlExecutorFactory:
        def factory(session: AsyncSession) -> ISqlExecutor:
            return SqlExecutor(session)

        return factory

    # ========== HTTP / Users Client ==========

    @provide(scope=Scope.APP)
    async def provide_http_client(self, settings: Settings) -> AsyncGenerator[AsyncClient]:
        async with AsyncClient(base_url=str(settings.users_service_url)) as client:
            yield client

    @provide(scope=Scope.APP)
    async def provide_event_publisher(self, settings: Settings) -> AsyncGenerator[IEventPublisher]:
        async with AsyncClient(
            base_url=str(settings.event_receiver_url),
            timeout=settings.event_publish_timeout_seconds,
        ) as client:
            yield EventPublisherClient(
                http_client=client,
                api_key=settings.event_receiver_api_key,
                attempts=settings.event_publish_attempts,
            )

    @provide(scope=Scope.APP)
    def provide_users_cache(self, settings: Settings) -> UsersCache:
        return UsersCache(ttl_seconds=settings.users_cache_ttl_seconds)

    @provide(scope=Scope.APP)
    def provide_users_client(self, http_client: AsyncClient, settings: Settings, cache: UsersCache) -> IUsersClient:
        return UsersClient(
            http_client=http_client,
            api_token=settings.users_service_api_token,
            cache=cache,
        )

    # ========== Notifier Client ==========

    @provide(scope=Scope.APP)
    async def provide_notifier_client(self, settings: Settings) -> AsyncGenerator[INotifierClient]:
        async with AsyncClient(base_url=str(settings.notifier_service_url)) as http_client:
            yield NotifierClient(
                http_client=http_client,
                api_token=settings.notifier_admin_token,
            )
