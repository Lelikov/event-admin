"""HTTP client for the event-notifier admin API."""

from typing import Any

import structlog
from httpx import AsyncClient


logger = structlog.get_logger(__name__)


class NotifierClient:
    def __init__(self, *, http_client: AsyncClient, api_token: str) -> None:
        self._client = http_client
        self._headers = {"Authorization": f"Bearer {api_token}"}

    async def get_config(self) -> dict[str, Any]:
        response = await self._client.get("/api/notifications/config", headers=self._headers)
        response.raise_for_status()
        return response.json()

    async def put_config(self, trigger_event: str, channel: str, body: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.put(
            f"/api/notifications/config/{trigger_event}/{channel}",
            json=body,
            headers=self._headers,
        )
        response.raise_for_status()
        return response.json()

    async def unisender_templates(self, *, refresh: bool) -> dict[str, Any]:
        response = await self._client.get(
            "/api/notifications/unisender-templates",
            params={"refresh": str(refresh).lower()},
            headers=self._headers,
        )
        response.raise_for_status()
        return response.json()

    async def telegram_preview(self, body: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post(
            "/api/notifications/telegram/preview",
            json=body,
            headers=self._headers,
        )
        response.raise_for_status()
        return response.json()
