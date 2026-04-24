from __future__ import annotations
from typing import TYPE_CHECKING, Protocol


if TYPE_CHECKING:
    from sqlalchemy.engine import RowMapping


class IAdminUsersDBAdapter(Protocol):
    async def get_by_email(self, email: str) -> RowMapping | None: ...
