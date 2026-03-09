from datetime import datetime

from pydantic import BaseModel

from event_admin.dto.bookings import BookingListItemDto, ParticipantDto


class ParticipantResponse(BaseModel):
    id: int
    email: str
    role: str | None
    time_zone: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_dto(cls, dto: ParticipantDto) -> ParticipantResponse:
        return cls(
            id=dto.id,
            email=dto.email,
            role=dto.role,
            time_zone=dto.time_zone,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
        )


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
