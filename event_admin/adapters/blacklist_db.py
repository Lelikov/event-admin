"""Blacklist repository: raw text() SQL via the shared SqlExecutor.

Writing blacklist_entries from event-admin is a sanctioned exception to the
read-only rule (same as admin_users). Effectiveness (is_active AND now within
[active_from, active_until]) is evaluated in SQL so every consumer sees the
same clock.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from event_admin.dto.blacklist import (
    UNSET,
    BlacklistCreateDto,
    BlacklistEntryDto,
    BlacklistListFiltersDto,
    BlacklistUpdateDto,
)
from event_admin.interfaces.blacklist import IBlacklistDBAdapter
from event_admin.interfaces.sql import ISqlExecutor


if TYPE_CHECKING:
    import uuid

    from sqlalchemy.engine import RowMapping


_COLUMNS = "id, field, value, is_active, active_from, active_until, comment, created_by, created_at, updated_at"

_EFFECTIVE_CONDITION = (
    "is_active AND (active_from IS NULL OR active_from <= now()) AND (active_until IS NULL OR active_until >= now())"
)

_UPDATABLE_FIELDS = ("field", "value", "is_active", "active_from", "active_until", "comment")


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards so a substring filter matches literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _row_to_dto(row: RowMapping) -> BlacklistEntryDto:
    return BlacklistEntryDto(
        id=row["id"],
        field=row["field"],
        value=row["value"],
        is_active=row["is_active"],
        active_from=row["active_from"],
        active_until=row["active_until"],
        comment=row["comment"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class BlacklistDBAdapter(IBlacklistDBAdapter):
    def __init__(self, sql_executor: ISqlExecutor) -> None:
        self._sql = sql_executor

    async def list_entries(
        self,
        filters: BlacklistListFiltersDto,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[BlacklistEntryDto], int]:
        conditions = ["TRUE"]
        values: dict = {"limit": limit, "offset": offset}
        if filters.field is not None:
            conditions.append("field = :field")
            values["field"] = filters.field
        if filters.value_contains is not None:
            conditions.append("value ILIKE '%' || :value_contains || '%' ESCAPE '\\'")
            values["value_contains"] = _escape_like(filters.value_contains)
        if filters.only_effective:
            conditions.append(_EFFECTIVE_CONDITION)
        where = " AND ".join(conditions)

        count_row = await self._sql.fetch_one(
            f"SELECT count(*) AS total FROM blacklist_entries WHERE {where}",  # noqa: S608
            {k: v for k, v in values.items() if k not in ("limit", "offset")},
        )
        rows = await self._sql.fetch_all(
            f"SELECT {_COLUMNS} FROM blacklist_entries WHERE {where} "  # noqa: S608
            "ORDER BY created_at DESC, id LIMIT :limit OFFSET :offset",
            values,
        )
        total = count_row["total"] if count_row is not None else 0
        return [_row_to_dto(row) for row in rows], total

    async def get_entry(self, entry_id: uuid.UUID) -> BlacklistEntryDto | None:
        row = await self._sql.fetch_one(
            f"SELECT {_COLUMNS} FROM blacklist_entries WHERE id = :entry_id",  # noqa: S608
            {"entry_id": entry_id},
        )
        if row is None:
            return None
        return _row_to_dto(row)

    async def create_entry(self, data: BlacklistCreateDto) -> BlacklistEntryDto:
        row = await self._sql.execute(
            "INSERT INTO blacklist_entries"  # noqa: S608
            " (field, value, is_active, active_from, active_until, comment, created_by)"
            " VALUES (:field, :value, :is_active, :active_from, :active_until, :comment, :created_by)"
            f" RETURNING {_COLUMNS}",
            {
                "field": data.field,
                "value": data.value,
                "is_active": data.is_active,
                "active_from": data.active_from,
                "active_until": data.active_until,
                "comment": data.comment,
                "created_by": data.created_by,
            },
        )
        return _row_to_dto(row)

    async def update_entry(self, entry_id: uuid.UUID, data: BlacklistUpdateDto) -> BlacklistEntryDto | None:
        updates = {name: getattr(data, name) for name in _UPDATABLE_FIELDS if getattr(data, name) is not UNSET}
        set_clause = ", ".join([*(f"{name} = :{name}" for name in updates), "updated_at = now()"])
        row = await self._sql.execute(
            f"UPDATE blacklist_entries SET {set_clause} WHERE id = :entry_id RETURNING {_COLUMNS}",  # noqa: S608
            {**updates, "entry_id": entry_id},
        )
        if row is None:
            return None
        return _row_to_dto(row)

    async def delete_entry(self, entry_id: uuid.UUID) -> bool:
        row = await self._sql.execute(
            "DELETE FROM blacklist_entries WHERE id = :entry_id RETURNING id",
            {"entry_id": entry_id},
        )
        return row is not None

    async def list_active_values(self, field: str) -> list[str]:
        rows = await self._sql.fetch_all(
            f"SELECT value FROM blacklist_entries WHERE field = :field AND {_EFFECTIVE_CONDITION}",  # noqa: S608
            {"field": field},
        )
        return [row["value"] for row in rows]
