from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class BookingListFiltersDto:
    booking_uids: list[str] = ()
    current_statuses: list[str] = ()
    current_organizer_participant_ref_ids: list[int] = ()
    current_client_participant_ref_ids: list[int] = ()


@dataclass(slots=True, frozen=True)
class ParticipantDto:
    id: int
    email: str
    role: str | None
    time_zone: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class BookingListItemDto:
    id: int
    booking_uid: str
    first_seen_at: datetime
    last_seen_at: datetime
    start_time: datetime | None
    end_time: datetime | None
    current_status: str | None
    created_at: datetime
    updated_at: datetime
    organizer_participant: ParticipantDto | None
    client_participant: ParticipantDto | None
