"""HTTP client for the users service."""

import uuid
from typing import Any

import structlog
from httpx import AsyncClient

from event_admin.services.users_cache import UsersCache


logger = structlog.get_logger(__name__)


class UsersClient:
    def __init__(self, *, http_client: AsyncClient, api_token: str, cache: UsersCache) -> None:
        self._client = http_client
        self._headers = {"Authorization": f"Bearer {api_token}"}
        self._cache = cache

    async def get_user(self, user_id: uuid.UUID) -> dict[str, Any]:
        cached = self._cache.get_user(user_id)
        if cached is not None:
            logger.debug("Users cache hit", user_id=str(user_id))
            return cached
        response = await self._client.get(
            f"/api/users/id/{user_id}",
            headers=self._headers,
        )
        response.raise_for_status()
        data = response.json()
        self._cache.set_user(user_id, data)
        logger.debug("Fetched user from users service", user_id=str(user_id))
        return data

    async def get_users_by_ids(self, user_ids: list[uuid.UUID]) -> dict[str, Any]:
        cached_items: list[dict[str, Any]] = []
        missing_ids: list[uuid.UUID] = []

        for uid in user_ids:
            cached = self._cache.get_user(uid)
            if cached is not None:
                cached_items.append(cached)
            else:
                missing_ids.append(uid)

        if missing_ids:
            response = await self._client.post(
                "/api/users/by-ids",
                json={"ids": [str(uid) for uid in missing_ids]},
                headers=self._headers,
            )
            response.raise_for_status()
            fetched = response.json()
            for item in fetched.get("items", []):
                self._cache.set_user(uuid.UUID(item["id"]), item)
                cached_items.append(item)
            logger.debug("Batch fetched users", requested=len(missing_ids), fetched=len(fetched.get("items", [])))

        return {"items": cached_items}

    async def list_users(
        self,
        *,
        email: str | None,
        role: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        cached = self._cache.get_list(email=email, role=role, limit=limit, offset=offset)
        if cached is not None:
            logger.debug("Users list cache hit", email=email, role=role)
            return cached
        params: dict[str, str | int] = {"limit": limit, "offset": offset}
        if email:
            params["email"] = email
        if role:
            params["role"] = role
        response = await self._client.get("/api/users", params=params, headers=self._headers)
        response.raise_for_status()
        data = response.json()
        self._cache.set_list(email=email, role=role, limit=limit, offset=offset, data=data)
        return data

    async def get_user_by_email_role(self, email: str, role: str) -> dict[str, Any] | None:
        response = await self._client.get(
            f"/api/users/roles/{role}/emails/{email}",
            headers=self._headers,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def get_email_changelog(self, user_id: uuid.UUID, *, limit: int, offset: int) -> dict[str, Any]:
        response = await self._client.get(
            f"/api/users/{user_id}/email-changelog",
            params={"limit": limit, "offset": offset},
            headers=self._headers,
        )
        response.raise_for_status()
        return response.json()
