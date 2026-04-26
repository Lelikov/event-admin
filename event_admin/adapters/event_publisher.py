"""HTTP client for publishing CloudEvents to event-receiver."""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from cloudevents.core.bindings.http import to_binary
from cloudevents.core.formats.json import JSONFormat
from cloudevents.core.v1.event import CloudEvent
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
                "time": datetime.now(UTC),
                "specversion": "1.0",
            },
            json.dumps(data).encode(),
        )
        message = to_binary(event, JSONFormat())
        headers = dict(message.headers)
        headers["Authorization"] = self._api_key
        headers["content-type"] = "application/json"

        response = await self._client.post(
            "/event/admin",
            content=message.body,
            headers=headers,
        )
        response.raise_for_status()
        logger.info(
            "CloudEvent published to event-receiver",
            source=source,
            event_type=event_type,
        )
