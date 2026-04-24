"""In-memory TTL cache for proxied users-service responses."""

import time
import uuid
from typing import Any

import structlog


logger = structlog.get_logger(__name__)


class UsersCache:
    def __init__(self, ttl_seconds: int = 300) -> None:
        self._ttl = ttl_seconds
        self._user_cache: dict[uuid.UUID, tuple[float, dict[str, Any]]] = {}
        self._list_cache: dict[tuple, tuple[float, dict[str, Any]]] = {}

    def get_user(self, user_id: uuid.UUID) -> dict[str, Any] | None:
        entry = self._user_cache.get(user_id)
        if entry is None:
            return None
        stored_at, data = entry
        if time.monotonic() - stored_at > self._ttl:
            del self._user_cache[user_id]
            return None
        return data

    def set_user(self, user_id: uuid.UUID, data: dict[str, Any]) -> None:
        self._user_cache[user_id] = (time.monotonic(), data)

    def get_list(self, *, email: str | None, role: str | None, limit: int, offset: int) -> dict[str, Any] | None:
        key = (email, role, limit, offset)
        entry = self._list_cache.get(key)
        if entry is None:
            return None
        stored_at, data = entry
        if time.monotonic() - stored_at > self._ttl:
            del self._list_cache[key]
            return None
        return data

    def set_list(self, *, email: str | None, role: str | None, limit: int, offset: int, data: dict[str, Any]) -> None:
        key = (email, role, limit, offset)
        self._list_cache[key] = (time.monotonic(), data)

    def invalidate(self) -> None:
        count = len(self._user_cache) + len(self._list_cache)
        self._user_cache.clear()
        self._list_cache.clear()
        logger.info("Users cache invalidated", evicted_entries=count)
