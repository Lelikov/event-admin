"""Frozen DTOs for the booking blacklist (inter-layer communication)."""

from __future__ import annotations
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import final


@final
class UnsetType:
    """Sentinel marking PATCH fields the client did not send (distinct from explicit null)."""

    _instance: UnsetType | None = None

    def __new__(cls) -> UnsetType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNSET"


UNSET = UnsetType()


@dataclass(slots=True, frozen=True)
class BlacklistEntryDto:
    id: uuid.UUID
    field: str
    value: str
    is_active: bool
    active_from: datetime | None
    active_until: datetime | None
    comment: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class BlacklistListFiltersDto:
    field: str | None = None
    value_contains: str | None = None
    only_effective: bool = False


@dataclass(slots=True, frozen=True)
class BlacklistCreateDto:
    field: str
    value: str
    is_active: bool
    active_from: datetime | None
    active_until: datetime | None
    comment: str | None
    created_by: str


@dataclass(slots=True, frozen=True)
class BlacklistUpdateDto:
    """PATCH payload; UNSET fields are left untouched by the adapter."""

    field: str | UnsetType = UNSET
    value: str | UnsetType = UNSET
    is_active: bool | UnsetType = UNSET
    active_from: datetime | None | UnsetType = UNSET
    active_until: datetime | None | UnsetType = UNSET
    comment: str | None | UnsetType = UNSET
