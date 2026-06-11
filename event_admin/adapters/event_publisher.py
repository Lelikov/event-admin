"""HTTP client for publishing CloudEvents to event-receiver."""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from cloudevents.core.bindings.http import to_binary
from cloudevents.core.formats.json import JSONFormat
from cloudevents.core.v1.event import CloudEvent
from httpx import AsyncClient, Response
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from event_admin.errors import EventPublishError


logger = structlog.get_logger(__name__)


class EventPublisherClient:
    """Publishes CloudEvents to event-receiver's POST /event/admin.

    Transport failures (timeouts, refused connections) are retried with
    exponential backoff; any final failure — transport or non-2xx — is
    raised as EventPublishError so routes can map it to 502 instead of
    surfacing an unhandled 500.
    """

    def __init__(self, *, http_client: AsyncClient, api_key: str, attempts: int = 3) -> None:
        self._client = http_client
        self._api_key = api_key
        self._attempts = attempts

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
        # event-receiver's /event/admin requires 'Authorization: Bearer <key>'
        # (token compared constant-time there; raw keys are rejected).
        headers["Authorization"] = f"Bearer {self._api_key}"
        headers["content-type"] = "application/json"

        try:
            response = await self._post_with_retry(content=message.body, headers=headers)
        except httpx.TransportError as exc:
            logger.exception(
                "Event publish failed: event-receiver unreachable",
                source=source,
                event_type=event_type,
                attempts=self._attempts,
                error=str(exc),
            )
            raise EventPublishError(
                event_type=event_type,
                source=source,
                upstream_status=None,
                detail=f"event-receiver unreachable after {self._attempts} attempts: {exc}",
            ) from exc

        if response.status_code >= 400:
            logger.error(
                "Event publish rejected by event-receiver",
                source=source,
                event_type=event_type,
                upstream_status=response.status_code,
                upstream_body=response.text[:500],
            )
            raise EventPublishError(
                event_type=event_type,
                source=source,
                upstream_status=response.status_code,
                detail=f"event-receiver returned {response.status_code}",
            )

        logger.info(
            "CloudEvent published to event-receiver",
            source=source,
            event_type=event_type,
        )

    async def _post_with_retry(self, *, content: bytes, headers: dict[str, str]) -> Response:
        retrying = AsyncRetrying(
            retry=retry_if_exception_type(httpx.TransportError),
            stop=stop_after_attempt(self._attempts),
            wait=wait_exponential(multiplier=0.2, max=2),
            reraise=True,
        )
        async for attempt in retrying:
            with attempt:
                return await self._client.post("/event/admin", content=content, headers=headers)
        raise AssertionError("unreachable: AsyncRetrying reraises on exhaustion")
