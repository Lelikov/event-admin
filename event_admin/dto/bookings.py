import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True, frozen=True)
class BookingListFiltersDto:
    booking_uids: tuple[str, ...] = ()
    current_statuses: tuple[str, ...] = ()
    current_organizer_user_ids: tuple[uuid.UUID, ...] = ()
    current_client_user_ids: tuple[uuid.UUID, ...] = ()


@dataclass(slots=True, frozen=True)
class ParticipantDto:
    user_id: uuid.UUID | None


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


@dataclass(slots=True, frozen=True)
class BookingOrganizerHistoryItemDto:
    id: int
    organizer_participant: ParticipantDto
    source_event_id: str | None
    effective_from: datetime
    created_at: datetime


@dataclass(slots=True, frozen=True)
class BookingMeetingLinkItemDto:
    id: int
    participant: ParticipantDto
    meeting_url: str
    source_event_id: str | None
    occurred_at: datetime
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class BookingEmailStatusHistoryItemDto:
    id: int
    notification_ref_id: int
    status: str | None
    status_event_time: datetime | None
    clicked_url: str | None
    source_event_id: str
    created_at: datetime


@dataclass(slots=True, frozen=True)
class BookingEmailNotificationItemDto:
    id: int
    participant: ParticipantDto | None
    trigger_event: str | None
    job_id: str
    sent_event_id: str | None
    sent_at: datetime | None
    last_status: str | None
    last_status_event_time: datetime | None
    last_status_event_id: str | None
    last_clicked_url: str | None
    created_at: datetime
    updated_at: datetime
    status_history: tuple[BookingEmailStatusHistoryItemDto, ...]


@dataclass(slots=True, frozen=True)
class BookingTelegramNotificationItemDto:
    id: int
    participant: ParticipantDto | None
    trigger_event: str | None
    source_event_id: str
    sent_at: datetime
    created_at: datetime


@dataclass(slots=True, frozen=True)
class BookingChatEventItemDto:
    id: int
    raw_event_id: str
    provider: str
    chat_event_type: str
    message_id: str | None
    participant: ParticipantDto | None
    is_read: bool | None
    text_preview: str | None
    occurred_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class BookingVideoEventItemDto:
    id: int
    raw_event_id: str
    video_event_type: str
    participant_role: str | None
    participant: ParticipantDto | None
    event_time: datetime | None
    payload: dict[str, Any]


@dataclass(slots=True, frozen=True)
class BookingLifecycleEventItemDto:
    id: int
    raw_event_id: str
    action: str
    organizer_participant: ParticipantDto | None
    client_participant: ParticipantDto | None
    details: dict[str, Any] | None
    occurred_at: datetime
    created_at: datetime


@dataclass(slots=True, frozen=True)
class BookingDetailsDto:
    id: int
    booking_uid: str
    first_seen_at: datetime
    last_seen_at: datetime
    start_time: datetime | None
    end_time: datetime | None
    current_status: str | None
    created_at: datetime
    updated_at: datetime
    current_organizer_participant: ParticipantDto | None
    current_client_participant: ParticipantDto | None
    organizer_history: tuple[BookingOrganizerHistoryItemDto, ...]
    meeting_links: tuple[BookingMeetingLinkItemDto, ...]
    email_notifications: tuple[BookingEmailNotificationItemDto, ...]
    telegram_notifications: tuple[BookingTelegramNotificationItemDto, ...]
    chat_events: tuple[BookingChatEventItemDto, ...]
    video_events: tuple[BookingVideoEventItemDto, ...]
    lifecycle_events: tuple[BookingLifecycleEventItemDto, ...]


@dataclass(slots=True, frozen=True)
class BookingFutureBouncedEmailItemDto:
    id: int
    booking_uid: str
    start_date: datetime
    end_time: datetime | None
    current_status: str | None
    organizer_participant: ParticipantDto | None
    client_participant: ParticipantDto | None
    email_bounce_statuses: tuple[str, ...]
