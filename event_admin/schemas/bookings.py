import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from event_admin.dto.bookings import (
    BookingChatEventItemDto,
    BookingDetailsDto,
    BookingEmailNotificationItemDto,
    BookingEmailStatusHistoryItemDto,
    BookingFutureBouncedEmailItemDto,
    BookingLifecycleEventItemDto,
    BookingListItemDto,
    BookingMeetingLinkItemDto,
    BookingOrganizerHistoryItemDto,
    BookingTelegramNotificationItemDto,
    BookingVideoEventItemDto,
    ParticipantDto,
)


class ParticipantResponse(BaseModel):
    user_id: uuid.UUID | None

    @classmethod
    def from_dto(cls, dto: ParticipantDto) -> ParticipantResponse:
        return cls(user_id=dto.user_id)


class BookingListItemResponse(BaseModel):
    id: int
    booking_uid: str
    first_seen_at: datetime
    last_seen_at: datetime
    start_time: datetime | None
    end_time: datetime | None
    current_status: str | None
    created_at: datetime
    updated_at: datetime
    organizer_participant: ParticipantResponse | None
    client_participant: ParticipantResponse | None

    @classmethod
    def from_dto(cls, dto: BookingListItemDto) -> BookingListItemResponse:
        return cls(
            id=dto.id,
            booking_uid=dto.booking_uid,
            first_seen_at=dto.first_seen_at,
            last_seen_at=dto.last_seen_at,
            start_time=dto.start_time,
            end_time=dto.end_time,
            current_status=dto.current_status,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
            organizer_participant=(
                ParticipantResponse.from_dto(dto.organizer_participant)
                if dto.organizer_participant is not None
                else None
            ),
            client_participant=(
                ParticipantResponse.from_dto(dto.client_participant) if dto.client_participant is not None else None
            ),
        )


class BookingOrganizerHistoryItemResponse(BaseModel):
    id: int
    organizer_participant: ParticipantResponse
    effective_from: datetime

    @classmethod
    def from_dto(cls, dto: BookingOrganizerHistoryItemDto) -> BookingOrganizerHistoryItemResponse:
        # source_event_id, created_at omitted: internal audit fields not needed in API response
        return cls(
            id=dto.id,
            organizer_participant=ParticipantResponse.from_dto(dto.organizer_participant),
            effective_from=dto.effective_from,
        )


class BookingMeetingLinkItemResponse(BaseModel):
    id: int
    participant: ParticipantResponse
    meeting_url: str
    created_at: datetime
    click_count: int | None = None

    @classmethod
    def from_dto(cls, dto: BookingMeetingLinkItemDto) -> BookingMeetingLinkItemResponse:
        # source_event_id, occurred_at, updated_at omitted: internal audit fields not needed in API response
        return cls(
            id=dto.id,
            participant=ParticipantResponse.from_dto(dto.participant),
            meeting_url=dto.meeting_url,
            created_at=dto.created_at,
            click_count=dto.click_count,
        )


class BookingEmailStatusHistoryItemResponse(BaseModel):
    id: int
    status: str | None
    clicked_url: str | None
    created_at: datetime

    @classmethod
    def from_dto(cls, dto: BookingEmailStatusHistoryItemDto) -> BookingEmailStatusHistoryItemResponse:
        # notification_ref_id, status_event_time, source_event_id omitted:
        # internal tracking fields not needed in API response
        return cls(
            id=dto.id,
            status=dto.status,
            clicked_url=dto.clicked_url,
            created_at=dto.created_at,
        )


class BookingEmailNotificationItemResponse(BaseModel):
    id: int
    participant: ParticipantResponse | None
    recipient_email: str | None
    trigger_event: str | None
    sent_at: datetime | None
    last_status: str | None
    status_history: list[BookingEmailStatusHistoryItemResponse]

    @classmethod
    def from_dto(cls, dto: BookingEmailNotificationItemDto) -> BookingEmailNotificationItemResponse:
        # job_id, sent_event_id, last_status_event_time, last_status_event_id, last_clicked_url,
        # created_at, updated_at omitted: internal tracking/audit fields not needed in API response
        return cls(
            id=dto.id,
            participant=(ParticipantResponse.from_dto(dto.participant) if dto.participant else None),
            recipient_email=dto.recipient_email,
            trigger_event=dto.trigger_event,
            sent_at=dto.sent_at,
            last_status=dto.last_status,
            status_history=[BookingEmailStatusHistoryItemResponse.from_dto(item) for item in dto.status_history],
        )


class BookingTelegramNotificationItemResponse(BaseModel):
    id: int
    participant: ParticipantResponse | None
    recipient_email: str | None
    trigger_event: str | None
    source_event_id: str
    sent_at: datetime
    created_at: datetime

    @classmethod
    def from_dto(cls, dto: BookingTelegramNotificationItemDto) -> BookingTelegramNotificationItemResponse:
        return cls(
            id=dto.id,
            participant=(ParticipantResponse.from_dto(dto.participant) if dto.participant else None),
            recipient_email=dto.recipient_email,
            trigger_event=dto.trigger_event,
            source_event_id=dto.source_event_id,
            sent_at=dto.sent_at,
            created_at=dto.created_at,
        )


class BookingChatEventItemResponse(BaseModel):
    id: int
    chat_event_type: str
    participant: ParticipantResponse | None
    is_read: bool | None
    text_preview: str | None
    occurred_at: datetime
    updated_at: datetime

    @classmethod
    def from_dto(cls, dto: BookingChatEventItemDto) -> BookingChatEventItemResponse:
        return cls(
            id=dto.id,
            chat_event_type=dto.chat_event_type,
            participant=(ParticipantResponse.from_dto(dto.participant) if dto.participant else None),
            is_read=dto.is_read,
            text_preview=dto.text_preview,
            occurred_at=dto.occurred_at,
            updated_at=dto.updated_at,
        )


class BookingVideoEventItemResponse(BaseModel):
    id: int
    raw_event_id: str
    video_event_type: str
    participant_role: str | None
    participant: ParticipantResponse | None
    event_time: datetime | None
    payload: dict[str, Any]

    @classmethod
    def from_dto(cls, dto: BookingVideoEventItemDto) -> BookingVideoEventItemResponse:
        return cls(
            id=dto.id,
            raw_event_id=dto.raw_event_id,
            video_event_type=dto.video_event_type,
            participant_role=dto.participant_role,
            participant=(ParticipantResponse.from_dto(dto.participant) if dto.participant else None),
            event_time=dto.event_time,
            payload=dto.payload,
        )


class BookingLifecycleEventItemResponse(BaseModel):
    id: int
    action: str
    organizer_participant: ParticipantResponse | None
    client_participant: ParticipantResponse | None
    details: dict[str, Any] | None
    occurred_at: datetime

    @classmethod
    def from_dto(cls, dto: BookingLifecycleEventItemDto) -> BookingLifecycleEventItemResponse:
        return cls(
            id=dto.id,
            action=dto.action,
            organizer_participant=(
                ParticipantResponse.from_dto(dto.organizer_participant) if dto.organizer_participant else None
            ),
            client_participant=(
                ParticipantResponse.from_dto(dto.client_participant) if dto.client_participant else None
            ),
            details=dto.details,
            occurred_at=dto.occurred_at,
        )


class BookingDetailsResponse(BaseModel):
    id: int
    booking_uid: str
    first_seen_at: datetime
    last_seen_at: datetime
    start_time: datetime | None
    end_time: datetime | None
    current_status: str | None
    created_at: datetime
    updated_at: datetime
    current_organizer_participant: ParticipantResponse | None
    current_client_participant: ParticipantResponse | None
    organizer_history: list[BookingOrganizerHistoryItemResponse]
    meeting_links: list[BookingMeetingLinkItemResponse]
    email_notifications: list[BookingEmailNotificationItemResponse]
    telegram_notifications: list[BookingTelegramNotificationItemResponse]
    chat_events: list[BookingChatEventItemResponse]
    video_events: list[BookingVideoEventItemResponse]
    lifecycle_events: list[BookingLifecycleEventItemResponse]

    @classmethod
    def from_dto(cls, dto: BookingDetailsDto) -> BookingDetailsResponse:
        return cls(
            id=dto.id,
            booking_uid=dto.booking_uid,
            first_seen_at=dto.first_seen_at,
            last_seen_at=dto.last_seen_at,
            start_time=dto.start_time,
            end_time=dto.end_time,
            current_status=dto.current_status,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
            current_organizer_participant=(
                ParticipantResponse.from_dto(dto.current_organizer_participant)
                if dto.current_organizer_participant
                else None
            ),
            current_client_participant=(
                ParticipantResponse.from_dto(dto.current_client_participant) if dto.current_client_participant else None
            ),
            organizer_history=[BookingOrganizerHistoryItemResponse.from_dto(item) for item in dto.organizer_history],
            meeting_links=[BookingMeetingLinkItemResponse.from_dto(item) for item in dto.meeting_links],
            email_notifications=[
                BookingEmailNotificationItemResponse.from_dto(item) for item in dto.email_notifications
            ],
            telegram_notifications=[
                BookingTelegramNotificationItemResponse.from_dto(item) for item in dto.telegram_notifications
            ],
            chat_events=[BookingChatEventItemResponse.from_dto(item) for item in dto.chat_events],
            video_events=[BookingVideoEventItemResponse.from_dto(item) for item in dto.video_events],
            lifecycle_events=[BookingLifecycleEventItemResponse.from_dto(item) for item in dto.lifecycle_events],
        )


class BookingFutureBouncedEmailItemResponse(BaseModel):
    id: int
    booking_uid: str
    start_date: datetime
    end_time: datetime | None
    current_status: str | None
    organizer_participant: ParticipantResponse | None
    client_participant: ParticipantResponse | None
    email_bounce_statuses: list[str]

    @classmethod
    def from_dto(cls, dto: BookingFutureBouncedEmailItemDto) -> BookingFutureBouncedEmailItemResponse:
        return cls(
            id=dto.id,
            booking_uid=dto.booking_uid,
            start_date=dto.start_date,
            end_time=dto.end_time,
            current_status=dto.current_status,
            organizer_participant=(
                ParticipantResponse.from_dto(dto.organizer_participant)
                if dto.organizer_participant is not None
                else None
            ),
            client_participant=(
                ParticipantResponse.from_dto(dto.client_participant) if dto.client_participant is not None else None
            ),
            email_bounce_statuses=list(dto.email_bounce_statuses),
        )
