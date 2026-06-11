from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from logging import getLevelNamesMapping

import structlog
from dishka import Provider, make_async_container
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from event_admin.config import Settings, get_settings
from event_admin.ioc import AppProvider
from event_admin.logger import setup_logger
from event_admin.middleware import JWTAuthMiddleware
from event_admin.routes import root_router


logger = structlog.get_logger(__name__)

PUBLIC_PATHS = frozenset({"/auth/login", "/health", "/api/users/cache/invalidate"})


def create_app(settings: Settings | None = None, provider: Provider | None = None) -> FastAPI:
    """Application factory: single Settings instance shared by DI, middleware, and CORS."""
    settings = settings or get_settings()
    container = make_async_container(provider or AppProvider(settings), FastapiProvider())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        log_level = getLevelNamesMapping().get(settings.log_level)
        setup_logger(log_level=log_level, console_render=settings.debug)
        logger.info(
            "Starting event admin application",
            log_level=settings.log_level,
            debug=settings.debug,
        )
        yield
        logger.info("Shutting down event admin application")
        await container.close()
        logger.info("Event admin application shutdown complete")

    app = FastAPI(title="event-admin", version="0.1.0", lifespan=lifespan)
    setup_dishka(container=container, app=app)
    app.include_router(root_router)

    app.add_middleware(
        JWTAuthMiddleware,
        settings=settings,
        public_paths=PUBLIC_PATHS,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app


app = create_app()
