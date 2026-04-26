"""HTTP client for publishing CloudEvents to event-receiver."""

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from cloudevents.core.v1.event import CloudEvent
from cloudevents.v1.http.http_methods import to_binary
from httpx import AsyncClient


logger = structlog.get_logger(__name__)


class EventPublisherClient:
    def __init__(self, *, http_client: AsyncClient, api_key: str) -> None:
        self._client = http_client
        self._api_key = api_key

    async def publish(
        self,
        *,
        source: str,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        event = CloudEvent(
            {
                "type": event_type,
                "source": source,
                "id": str(uuid.uuid4()),
                "time": datetime.now(UTC).isoformat(),
                "specversion": "1.0",
            },
            data,
        )
        headers, body = to_binary(event)
        headers["Authorization"] = self._api_key

        response = await self._client.post(
            "/event/admin",
            content=body,
            headers=dict(headers),
        )
        response.raise_for_status()
        logger.info(
            "CloudEvent published to event-receiver",
            source=source,
            event_type=event_type,
        )
