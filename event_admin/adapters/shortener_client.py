"""HTTP client for event-shortener's stats endpoint (best-effort)."""

import httpx
import structlog
from httpx import AsyncClient


logger = structlog.get_logger(__name__)


class ShortenerClient:
    def __init__(self, *, http_client: AsyncClient, api_key: str) -> None:
        self._client = http_client
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def get_click_count(self, ident: str) -> int | None:
        """Return the click count for an ident, or None on any failure.

        The shortener is never on the booking-detail critical path, so a missing
        ident, an unreachable shortener, or a 5xx all degrade to None.
        """
        try:
            response = await self._client.get(f"/api/v1/urls/{ident}/stats", headers=self._headers)
        except httpx.HTTPError as exc:
            logger.warning("Shortener unreachable for click count", ident=ident, error=str(exc))
            return None
        if response.status_code != 200:
            return None
        return response.json().get("click_count")
