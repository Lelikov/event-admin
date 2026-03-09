import structlog
from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter


root_router = APIRouter(route_class=DishkaRoute)
logger = structlog.get_logger(__name__)


@root_router.get("/health")
async def health() -> dict[str, str]:
    logger.debug("Health check requested")
    return {"status": "ok"}
