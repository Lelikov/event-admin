"""Interface for users service client."""

import uuid
from typing import Any, Protocol


class IUsersClient(Protocol):
    async def get_user(self, user_id: uuid.UUID) -> dict[str, Any]: ...
    async def get_users_by_ids(self, user_ids: list[uuid.UUID]) -> dict[str, Any]: ...
    async def list_users(self, *, email: str | None, role: str | None, limit: int, offset: int) -> dict[str, Any]: ...
