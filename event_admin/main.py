from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from logging import getLevelNamesMapping

import structlog
from dishka import Provider, make_async_container
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from event_admin.config import Settings, get_settings
from event_admin.errors import EventPublishError
from event_admin.ioc import AppProvider
from event_admin.logger import setup_logger
from event_admin.metrics import HttpMetricsMiddleware
from event_admin.middleware import JWTAuthMiddleware
from event_admin.routes import root_router
from event_admin.telemetry import instrument_asyncpg, instrument_fastapi, setup_tracing


logger = structlog.get_logger(__name__)

PUBLIC_PATHS = frozenset(
    {
        "/auth/login",
        "/health",
        "/ready",
        "/metrics",
        "/api/users/cache/invalidate",
        # Service endpoint for event-booking; guarded by BLACKLIST_SERVICE_TOKEN in the route.
        "/api/blacklist/active",
    },
)


def _event_publish_error_handler(_: Request, exc: EventPublishError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={
            "detail": {
                "code": "event_publish_failed",
                "message": "Failed to publish event to event-receiver; the action was NOT applied",
            },
            "event_type": exc.event_type,
            "upstream_status": exc.upstream_status,
        },
    )


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
    setup_tracing()
    instrument_fastapi(app)
    instrument_asyncpg()
    setup_dishka(container=container, app=app)
    app.include_router(root_router)
    app.add_exception_handler(EventPublishError, _event_publish_error_handler)

    # Middleware ordering is significant: Starlette wraps the LAST-added
    # middleware OUTERMOST. CORSMiddleware must be added last so that 401s
    # produced by JWTAuthMiddleware still carry CORS headers. Do not reorder.
    app.add_middleware(
        JWTAuthMiddleware,
        settings=settings,
        public_paths=PUBLIC_PATHS,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        # Auth uses an explicit Authorization: Bearer header (not cookies),
        # so credentialed CORS is unnecessary; methods/headers are restricted
        # to what the SPA actually uses.
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )
    # Outermost: observes every request (auth rejections included; those have no
    # matched route yet and are recorded as route="unmatched").
    app.add_middleware(HttpMetricsMiddleware)
    return app


app = create_app()
