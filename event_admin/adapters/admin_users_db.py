from __future__ import annotations
from typing import TYPE_CHECKING

from event_admin.interfaces.admin_users import IAdminUsersDBAdapter
from event_admin.interfaces.sql import ISqlExecutor


if TYPE_CHECKING:
    from sqlalchemy.engine import RowMapping


class AdminUsersDBAdapter(IAdminUsersDBAdapter):
    def __init__(self, sql_executor: ISqlExecutor) -> None:
        self._sql = sql_executor

    async def get_by_email(self, email: str) -> RowMapping | None:
        return await self._sql.fetch_one(
            "SELECT id, email, hashed_password, totp_secret, role, is_active FROM admin_users WHERE email = :email",
            {"email": email},
        )
