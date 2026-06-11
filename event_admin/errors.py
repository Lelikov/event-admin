"""Domain errors raised by adapters and mapped to HTTP responses in main.py."""

from __future__ import annotations


class EventPublishError(Exception):
    """Publishing a CloudEvent to event-receiver failed after retries.

    upstream_status is the HTTP status returned by event-receiver,
    or None for transport-level failures (timeout, connection refused).
    """

    def __init__(self, *, event_type: str, source: str, upstream_status: int | None, detail: str) -> None:
        self.event_type = event_type
        self.source = source
        self.upstream_status = upstream_status
        self.detail = detail
        super().__init__(detail)
