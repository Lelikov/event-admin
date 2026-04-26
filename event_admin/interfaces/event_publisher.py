"""Interface for publishing CloudEvents to event-receiver."""

from typing import Any, Protocol


class IEventPublisher(Protocol):
    async def publish(
        self,
        *,
        source: str,
        event_type: str,
        data: dict[str, Any],
    ) -> None: ...
