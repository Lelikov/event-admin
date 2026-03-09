from collections.abc import AsyncGenerator

import structlog
from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from event_admin.adapters.bookings_db import BookingsDBAdapter
from event_admin.adapters.sql import SqlExecutor
from event_admin.config import Settings
from event_admin.controllers.bookings import BookingsController
from event_admin.interfaces.bookings import IBookingsController, IBookingsDBAdapter
from event_admin.interfaces.sql import ISqlExecutor, ISqlExecutorFactory


logger = structlog.get_logger(__name__)


class AppProvider(Provider):
    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        settings = Settings()
        logger.info(
            "Settings initialized",
            debug=settings.debug,
            log_level=settings.log_level,
        )
        return settings

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
