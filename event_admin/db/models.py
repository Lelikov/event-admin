import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from event_admin.db.base import Base


class AdminUser(Base):
    """Admin panel user. Roles: 'admin' (full access) | 'user' (read-only).

    Migration SQL:
        CREATE TABLE admin_users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email TEXT NOT NULL UNIQUE,
            hashed_password TEXT NOT NULL,
            totp_secret TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX ix_admin_users_email ON admin_users (email);
    """

    __tablename__ = "admin_users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    totp_secret: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'user'"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        server_onupdate=text("now()"),
    )

    __table_args__ = (Index("ix_admin_users_email", "email"),)


class BookingRecord(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    booking_uid: Mapped[str] = mapped_column(Text, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    organizer_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    client_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
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
    organizer_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
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
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
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
            "user_id",
            name="uq_bml_booking_ref_id_user_id",
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
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
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
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
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
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
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
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
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
