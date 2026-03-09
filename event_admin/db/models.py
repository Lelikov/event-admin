from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from event_admin.db.base import Base


if TYPE_CHECKING:
    from datetime import datetime


class Event(Base):
    __tablename__ = "events"

    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    booking_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    hash: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        Index(
            "ix_events_booking_id_occurred_at_desc",
            "booking_id",
            text("occurred_at DESC"),
        ),
        Index(
            "ix_events_event_type_occurred_at_desc",
            "event_type",
            text("occurred_at DESC"),
        ),
        Index(
            "uq_events_booking_id_event_type_source_hash",
            "booking_id",
            "event_type",
            "source",
            "hash",
            unique=True,
        ),
    )


class BookingRecord(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    booking_uid: Mapped[str] = mapped_column(Text, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_organizer_participant_ref_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("participants.id", ondelete="SET NULL"),
        nullable=True,
    )
    current_client_participant_ref_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("participants.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        server_onupdate=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint("booking_uid", name="uq_bookings_booking_uid"),
        Index(
            "ix_bookings_last_seen_desc",
            text("last_seen_at DESC"),
        ),
    )


class BookingOrganizerHistory(Base):
    __tablename__ = "booking_organizer_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    booking_ref_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
    )
    organizer_participant_ref_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("participants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_event_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("events.event_id", ondelete="SET NULL"),
        nullable=True,
    )
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        Index(
            "ix_boh_booking_effective_from_desc",
            "booking_ref_id",
            text("effective_from DESC"),
        ),
    )


class BookingMeetingLink(Base):
    __tablename__ = "booking_meeting_links"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    booking_ref_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
    )
    participant_ref_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("participants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    meeting_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("events.event_id", ondelete="SET NULL"),
        nullable=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        server_onupdate=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint(
            "booking_ref_id",
            "participant_ref_id",
            name="uq_bml_booking_ref_id_participant_ref_id",
        ),
        Index(
            "ix_bml_booking_ref_id",
            "booking_ref_id",
        ),
    )


class BookingEmailNotification(Base):
    __tablename__ = "booking_email_notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    booking_ref_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
    )
    participant_ref_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("participants.id", ondelete="SET NULL"),
        nullable=True,
    )
    trigger_event: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_id: Mapped[str] = mapped_column(Text, nullable=False)
    sent_event_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("events.event_id", ondelete="SET NULL"),
        nullable=True,
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_status_event_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_status_event_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("events.event_id", ondelete="SET NULL"),
        nullable=True,
    )
    last_clicked_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        server_onupdate=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint("job_id", name="uq_booking_email_notifications_job_id"),
        Index(
            "ix_ben_booking_ref_id",
            "booking_ref_id",
        ),
        Index(
            "ix_ben_booking_ref_last_status_time_desc",
            "booking_ref_id",
            text("last_status_event_time DESC"),
        ),
    )


class BookingTelegramNotification(Base):
    __tablename__ = "booking_telegram_notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    booking_ref_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
    )
    participant_ref_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("participants.id", ondelete="SET NULL"),
        nullable=True,
    )
    trigger_event: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_event_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("events.event_id", ondelete="CASCADE"),
        nullable=False,
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint("source_event_id", name="uq_btn_source_event_id"),
        Index("ix_btn_booking_ref_sent_at_desc", "booking_ref_id", text("sent_at DESC")),
    )


class BookingEmailStatusHistory(Base):
    __tablename__ = "booking_email_status_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    notification_ref_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("booking_email_notifications.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_event_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    clicked_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_event_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("events.event_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint("source_event_id", name="uq_besh_source_event_id"),
        Index(
            "ix_besh_notification_ref_status_time_desc",
            "notification_ref_id",
            text("status_event_time DESC"),
        ),
    )


class BookingChatEvent(Base):
    __tablename__ = "booking_chat_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    booking_ref_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
    )
    raw_event_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("events.event_id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    chat_event_type: Mapped[str] = mapped_column(Text, nullable=False)
    message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    participant_ref_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("participants.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_read: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    text_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        server_onupdate=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint("raw_event_id", name="uq_booking_chat_events_raw_event_id"),
        Index(
            "ix_bce_booking_ref_occurred_desc",
            "booking_ref_id",
            text("occurred_at DESC"),
        ),
        Index(
            "ix_bce_booking_ref_type_occurred_desc",
            "booking_ref_id",
            "chat_event_type",
            text("occurred_at DESC"),
        ),
    )


class BookingVideoEvent(Base):
    __tablename__ = "booking_video_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    booking_ref_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
    )
    raw_event_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("events.event_id", ondelete="CASCADE"),
        nullable=False,
    )
    video_event_type: Mapped[str] = mapped_column(Text, nullable=False)
    participant_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    participant_ref_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("participants.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    __table_args__ = (
        UniqueConstraint("raw_event_id", name="uq_booking_video_events_raw_event_id"),
        Index(
            "ix_bve_booking_ref_event_time_desc",
            "booking_ref_id",
            text("event_time DESC"),
        ),
        Index(
            "ix_bve_booking_ref_type_event_time_desc",
            "booking_ref_id",
            "video_event_type",
            text("event_time DESC"),
        ),
    )


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str | None] = mapped_column(Text, nullable=True)
    time_zone: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        server_onupdate=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint("email", name="uq_participants_email"),
        Index("ix_participants_role", "role"),
    )
