from __future__ import annotations
from typing import TYPE_CHECKING, Protocol


if TYPE_CHECKING:
    import uuid

    from event_admin.dto.blacklist import (
        BlacklistCreateDto,
        BlacklistEntryDto,
        BlacklistListFiltersDto,
        BlacklistUpdateDto,
    )


class IBlacklistDBAdapter(Protocol):
    """Blacklist repository (raw SQL over the shared SqlExecutor).

    Writing blacklist_entries from event-admin is a sanctioned exception to
    the read-only rule (same as admin_users).
    """

    async def list_entries(
        self,
        filters: BlacklistListFiltersDto,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[BlacklistEntryDto], int]: ...

    async def get_entry(self, entry_id: uuid.UUID) -> BlacklistEntryDto | None: ...

    async def create_entry(self, data: BlacklistCreateDto) -> BlacklistEntryDto: ...

    async def update_entry(self, entry_id: uuid.UUID, data: BlacklistUpdateDto) -> BlacklistEntryDto | None: ...

    async def delete_entry(self, entry_id: uuid.UUID) -> bool: ...

    async def list_active_values(self, field: str) -> list[str]: ...
