"""Pydantic request/response schemas for the booking blacklist API."""

from __future__ import annotations
import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field

from event_admin.dto.blacklist import BlacklistEntryDto


class BlacklistEntryResponse(BaseModel):
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

    @classmethod
    def from_dto(cls, dto: BlacklistEntryDto) -> Self:
        return cls(
            id=dto.id,
            field=dto.field,
            value=dto.value,
            is_active=dto.is_active,
            active_from=dto.active_from,
            active_until=dto.active_until,
            comment=dto.comment,
            created_by=dto.created_by,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
        )


class BlacklistListResponse(BaseModel):
    items: list[BlacklistEntryResponse]
    total: int
    limit: int
    offset: int


class BlacklistActiveResponse(BaseModel):
    """Service contract for event-booking: currently-effective values for one field."""

    field: str
    values: list[str]


class BlacklistCreateRequest(BaseModel):
    field: str = Field("client_email", min_length=1, max_length=64)
    value: str = Field(..., min_length=1, max_length=320)
    is_active: bool = True
    active_from: datetime | None = None
    active_until: datetime | None = None
    comment: str | None = Field(None, max_length=1000)


class BlacklistUpdateRequest(BaseModel):
    """PATCH body; omitted fields are left untouched (model_dump(exclude_unset=True))."""

    field: str | None = Field(None, min_length=1, max_length=64)
    value: str | None = Field(None, min_length=1, max_length=320)
    is_active: bool | None = None
    active_from: datetime | None = None
    active_until: datetime | None = None
    comment: str | None = Field(None, max_length=1000)
