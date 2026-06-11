"""Typed models for the /api/users proxy endpoints.

Response models are an explicit allowlist of fields forwarded from
event-users to the admin frontend — any future internal/sensitive upstream
fields (e.g. CRM identifiers) are dropped instead of leaking by default.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProxiedUserContact(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    channel: str
    contact_id: str
    created_at: datetime
    updated_at: datetime


class ProxiedUser(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None = None
    role: str
    time_zone: str | None = None
    contacts: list[ProxiedUserContact] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ProxiedUsersListResponse(BaseModel):
    items: list[ProxiedUser]
    total: int
    limit: int
    offset: int


class ProxiedUsersByIdsResponse(BaseModel):
    items: list[ProxiedUser]


class ProxiedEmailChangelogEntry(BaseModel):
    id: uuid.UUID
    old_email: str
    new_email: str
    changed_by: str
    changed_at: datetime


class ProxiedEmailChangelogResponse(BaseModel):
    items: list[ProxiedEmailChangelogEntry]
    total: int


class UsersByIdsRequest(BaseModel):
    ids: list[uuid.UUID] = Field(max_length=200)
