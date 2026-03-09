from contextlib import asynccontextmanager
from logging import getLevelNamesMapping
from typing import TYPE_CHECKING

import structlog
from dishka import make_async_container
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI

from event_admin.config import Settings
from event_admin.ioc import AppProvider
from event_admin.logger import setup_logger
from event_admin.routes import root_router


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


container = make_async_container(AppProvider(), FastapiProvider())
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    settings = await container.get(Settings)
    log_level = getLevelNamesMapping().get(settings.log_level)
    setup_logger(log_level=log_level, console_render=settings.debug)

    logger.info(
        "Starting event receiver application",
        log_level=settings.log_level,
        debug=settings.debug,
    )

    yield

    logger.info("Event receiver application shutdown complete")


app = FastAPI(title="event-admin", version="0.1.0", lifespan=lifespan)
setup_dishka(container=container, app=app)
app.include_router(root_router)
