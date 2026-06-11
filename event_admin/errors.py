"""Domain errors raised by adapters and mapped to HTTP responses in main.py."""

from __future__ import annotations

from fastapi import HTTPException


def http_error(status_code: int, code: str, message: str) -> HTTPException:
    """Build an HTTPException with a machine-readable detail object.

    Every error response carries ``detail = {"code": <stable_snake_case>,
    "message": <human text>}`` so clients (event-admin-frontend) key their
    translations on ``code`` instead of matching exact English prose.
    """
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


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
