import asyncio
from typing import TYPE_CHECKING

from event_admin.dto.bookings import (
    BookingChatEventItemDto,
    BookingDetailsDto,
    BookingEmailNotificationItemDto,
    BookingEmailStatusHistoryItemDto,
    BookingFutureBouncedEmailItemDto,
    BookingLifecycleEventItemDto,
    BookingListFiltersDto,
    BookingListItemDto,
    BookingMeetingLinkItemDto,
    BookingOrganizerHistoryItemDto,
    BookingTelegramNotificationItemDto,
    BookingVideoEventItemDto,
    ParticipantDto,
)
from event_admin.interfaces.bookings import IBookingsDBAdapter
from event_admin.interfaces.sql import ISqlExecutor


if TYPE_CHECKING:
    from sqlalchemy.engine import RowMapping


class BookingsDBAdapter(IBookingsDBAdapter):
    def __init__(self, sql_executor: ISqlExecutor) -> None:
        self.sql_executor = sql_executor

    async def list_bookings(
        self,
        filters: BookingListFiltersDto,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BookingListItemDto]:
        conditions: list[str] = []
        values: dict = {}

        if filters.booking_uids:
            conditions.append("b.booking_uid = ANY(:booking_uids)")
            values["booking_uids"] = list(filters.booking_uids)

        if filters.current_statuses:
            conditions.append("b.current_status = ANY(:current_statuses)")
            values["current_statuses"] = list(filters.current_statuses)

        if filters.current_organizer_user_ids:
            conditions.append("b.organizer_user_id = ANY(:current_organizer_user_ids)")
            values["current_organizer_user_ids"] = [str(uid) for uid in filters.current_organizer_user_ids]

        if filters.current_client_user_ids:
            conditions.append("b.client_user_id = ANY(:current_client_user_ids)")
            values["current_client_user_ids"] = [str(uid) for uid in filters.current_client_user_ids]

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        query = """
            SELECT
                b.id,
                b.booking_uid,
                b.first_seen_at,
                b.last_seen_at,
                b.start_time,
                b.end_time,
                b.current_status,
                b.created_at,
                b.updated_at,
                b.organizer_user_id,
                b.client_user_id
            FROM bookings b
        """

        if where_clause:
            query += f"\n{where_clause}"

        query += "\nORDER BY b.last_seen_at DESC"
        query += "\nLIMIT :limit OFFSET :offset"
        values["limit"] = limit
        values["offset"] = offset

        rows = await self.sql_executor.fetch_all(query, values)
        return [self._map_row_to_dto(row) for row in rows]

    async def get_booking_details(self, booking_uid: str) -> BookingDetailsDto | None:
        booking_row = await self.sql_executor.fetch_one(
            """
            SELECT
                b.id,
                b.booking_uid,
                b.first_seen_at,
                b.last_seen_at,
                b.start_time,
                b.end_time,
                b.current_status,
                b.created_at,
                b.updated_at,
                b.organizer_user_id AS current_organizer_user_id,
                b.client_user_id AS current_client_user_id
            FROM bookings b
            WHERE b.booking_uid = :booking_uid
            LIMIT 1
            """,
            {"booking_uid": booking_uid},
        )

        if booking_row is None:
            return None

        booking_ref_id = booking_row["id"]

        (
            organizer_history_rows,
            meeting_link_rows,
            email_notification_rows,
            telegram_notification_rows,
            chat_event_rows,
            video_event_rows,
            lifecycle_event_rows,
        ) = await asyncio.gather(
            self.sql_executor.fetch_all(
                """
                SELECT
                    boh.id,
                    boh.source_event_id,
                    boh.effective_from,
                    boh.created_at,
                    boh.organizer_user_id AS participant_user_id
                FROM booking_organizer_history boh
                WHERE boh.booking_ref_id = :booking_ref_id
                ORDER BY boh.effective_from DESC, boh.id DESC
                """,
                {"booking_ref_id": booking_ref_id},
            ),
            self.sql_executor.fetch_all(
                """
                SELECT
                    bml.id,
                    bml.meeting_url,
                    bml.source_event_id,
                    bml.occurred_at,
                    bml.created_at,
                    bml.updated_at,
                    bml.user_id AS participant_user_id
                FROM booking_meeting_links bml
                WHERE bml.booking_ref_id = :booking_ref_id
                ORDER BY bml.occurred_at DESC, bml.id DESC
                """,
                {"booking_ref_id": booking_ref_id},
            ),
            self.sql_executor.fetch_all(
                """
                SELECT
                    ben.id,
                    ben.trigger_event,
                    ben.job_id,
                    ben.sent_event_id,
                    ben.sent_at,
                    ben.last_status,
                    ben.last_status_event_time,
                    ben.last_status_event_id,
                    ben.last_clicked_url,
                    ben.created_at,
                    ben.updated_at,
                    ben.user_id AS participant_user_id
                FROM booking_email_notifications ben
                WHERE ben.booking_ref_id = :booking_ref_id
                ORDER BY ben.created_at DESC, ben.id DESC
                """,
                {"booking_ref_id": booking_ref_id},
            ),
            self.sql_executor.fetch_all(
                """
                SELECT
                    btn.id,
                    btn.trigger_event,
                    btn.source_event_id,
                    btn.sent_at,
                    btn.created_at,
                    btn.user_id AS participant_user_id
                FROM booking_telegram_notifications btn
                WHERE btn.booking_ref_id = :booking_ref_id
                ORDER BY btn.sent_at DESC, btn.id DESC
                """,
                {"booking_ref_id": booking_ref_id},
            ),
            self.sql_executor.fetch_all(
                """
                SELECT
                    bce.id,
                    bce.raw_event_id,
                    bce.provider,
                    bce.chat_event_type,
                    bce.message_id,
                    bce.is_read,
                    bce.text_preview,
                    bce.occurred_at,
                    bce.updated_at,
                    bce.user_id AS participant_user_id
                FROM booking_chat_events bce
                WHERE bce.booking_ref_id = :booking_ref_id AND bce.chat_event_type != 'message.read'
                ORDER BY bce.occurred_at ASC
                """,
                {"booking_ref_id": booking_ref_id},
            ),
            self.sql_executor.fetch_all(
                """
                SELECT
                    bve.id,
                    bve.raw_event_id,
                    bve.video_event_type,
                    bve.participant_role,
                    bve.event_time,
                    bve.payload,
                    bve.user_id AS participant_user_id
                FROM booking_video_events bve
                WHERE bve.booking_ref_id = :booking_ref_id
                ORDER BY bve.event_time DESC NULLS LAST, bve.id DESC
                """,
                {"booking_ref_id": booking_ref_id},
            ),
            self.sql_executor.fetch_all(
                """
                SELECT
                    ble.id,
                    ble.raw_event_id,
                    ble.action,
                    ble.organizer_user_id AS organizer_participant_user_id,
                    ble.client_user_id AS client_participant_user_id,
                    ble.details,
                    ble.occurred_at,
                    ble.created_at
                FROM booking_lifecycle_events ble
                WHERE ble.booking_ref_id = :booking_ref_id
                ORDER BY ble.occurred_at ASC, ble.id ASC
                """,
                {"booking_ref_id": booking_ref_id},
            ),
        )

        notification_ids = [row["id"] for row in email_notification_rows]
        email_status_history_rows: list[RowMapping] = []
        if notification_ids:
            email_status_history_rows = await self.sql_executor.fetch_all(
                """
                SELECT
                    besh.id,
                    besh.notification_ref_id,
                    besh.status,
                    besh.status_event_time,
                    besh.clicked_url,
                    besh.source_event_id,
                    besh.created_at
                FROM booking_email_status_history besh
                WHERE besh.notification_ref_id = ANY(:notification_ids)
                ORDER BY besh.status_event_time ASC NULLS LAST
                """,
                {"notification_ids": notification_ids},
            )

        status_history_by_notification: dict[int, list[BookingEmailStatusHistoryItemDto]] = {}
        for row in email_status_history_rows:
            item = BookingEmailStatusHistoryItemDto(
                id=row["id"],
                notification_ref_id=row["notification_ref_id"],
                status=row["status"],
                status_event_time=row["status_event_time"],
                clicked_url=row["clicked_url"],
                source_event_id=row["source_event_id"],
                created_at=row["created_at"],
            )
            status_history_by_notification.setdefault(row["notification_ref_id"], []).append(item)

        organizer_history = tuple(
            BookingOrganizerHistoryItemDto(
                id=row["id"],
                organizer_participant=self._map_prefixed_participant(row, "participant"),
                source_event_id=row["source_event_id"],
                effective_from=row["effective_from"],
                created_at=row["created_at"],
            )
            for row in organizer_history_rows
        )

        meeting_links = tuple(
            BookingMeetingLinkItemDto(
                id=row["id"],
                participant=self._map_prefixed_participant(row, "participant"),
                meeting_url=row["meeting_url"],
                source_event_id=row["source_event_id"],
                occurred_at=row["occurred_at"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in meeting_link_rows
        )

        email_notifications = tuple(
            BookingEmailNotificationItemDto(
                id=row["id"],
                participant=self._map_prefixed_participant_optional(row, "participant"),
                trigger_event=row["trigger_event"],
                job_id=row["job_id"],
                sent_event_id=row["sent_event_id"],
                sent_at=row["sent_at"],
                last_status=row["last_status"],
                last_status_event_time=row["last_status_event_time"],
                last_status_event_id=row["last_status_event_id"],
                last_clicked_url=row["last_clicked_url"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                status_history=tuple(status_history_by_notification.get(row["id"], [])),
            )
            for row in email_notification_rows
        )

        telegram_notifications = tuple(
            BookingTelegramNotificationItemDto(
                id=row["id"],
                participant=self._map_prefixed_participant_optional(row, "participant"),
                trigger_event=row["trigger_event"],
                source_event_id=row["source_event_id"],
                sent_at=row["sent_at"],
                created_at=row["created_at"],
            )
            for row in telegram_notification_rows
        )

        chat_events = tuple(
            BookingChatEventItemDto(
                id=row["id"],
                raw_event_id=row["raw_event_id"],
                provider=row["provider"],
                chat_event_type=row["chat_event_type"],
                message_id=row["message_id"],
                participant=self._map_prefixed_participant_optional(row, "participant"),
                is_read=row["is_read"],
                text_preview=row["text_preview"],
                occurred_at=row["occurred_at"],
                updated_at=row["updated_at"],
            )
            for row in chat_event_rows
        )

        video_events = tuple(
            BookingVideoEventItemDto(
                id=row["id"],
                raw_event_id=row["raw_event_id"],
                video_event_type=row["video_event_type"],
                participant_role=row["participant_role"],
                participant=self._map_prefixed_participant_optional(row, "participant"),
                event_time=row["event_time"],
                payload=row["payload"],
            )
            for row in video_event_rows
        )

        lifecycle_events = tuple(
            BookingLifecycleEventItemDto(
                id=row["id"],
                raw_event_id=row["raw_event_id"],
                action=row["action"],
                organizer_participant=self._map_prefixed_participant_optional(row, "organizer_participant"),
                client_participant=self._map_prefixed_participant_optional(row, "client_participant"),
                details=row["details"],
                occurred_at=row["occurred_at"],
                created_at=row["created_at"],
            )
            for row in lifecycle_event_rows
        )

        return BookingDetailsDto(
            id=booking_row["id"],
            booking_uid=booking_row["booking_uid"],
            first_seen_at=booking_row["first_seen_at"],
            last_seen_at=booking_row["last_seen_at"],
            start_time=booking_row["start_time"],
            end_time=booking_row["end_time"],
            current_status=booking_row["current_status"],
            created_at=booking_row["created_at"],
            updated_at=booking_row["updated_at"],
            current_organizer_participant=self._map_prefixed_participant_optional(
                booking_row,
                "current_organizer",
            ),
            current_client_participant=self._map_prefixed_participant_optional(
                booking_row,
                "current_client",
            ),
            organizer_history=organizer_history,
            meeting_links=meeting_links,
            email_notifications=email_notifications,
            telegram_notifications=telegram_notifications,
            chat_events=chat_events,
            video_events=video_events,
            lifecycle_events=lifecycle_events,
        )

    async def list_future_email_bounced_bookings(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BookingFutureBouncedEmailItemDto]:
        rows = await self.sql_executor.fetch_all(
            """
            SELECT
                b.id,
                b.booking_uid,
                b.start_time AS start_date,
                b.end_time,
                b.current_status,
                b.organizer_user_id,
                b.client_user_id,
                ARRAY_AGG(DISTINCT ben.last_status) FILTER (
                    WHERE ben.last_status IN ('hard_bounce', 'soft_bounce')
                ) AS email_bounce_statuses
            FROM bookings b
            JOIN booking_email_notifications ben ON ben.booking_ref_id = b.id
            WHERE b.start_time > now()
              AND ben.last_status IN ('hard_bounce', 'soft_bounce')
            GROUP BY
                b.id,
                b.booking_uid,
                b.start_time,
                b.end_time,
                b.current_status,
                b.organizer_user_id,
                b.client_user_id
            ORDER BY b.start_time ASC, b.id ASC
            LIMIT :limit OFFSET :offset
            """,
            {"limit": limit, "offset": offset},
        )

        return [self._map_future_bounced_row_to_dto(row) for row in rows]

    @staticmethod
    def _map_row_to_dto(row: RowMapping) -> BookingListItemDto:
        organizer_participant = (
            ParticipantDto(user_id=row["organizer_user_id"]) if row["organizer_user_id"] is not None else None
        )
        client_participant = (
            ParticipantDto(user_id=row["client_user_id"]) if row["client_user_id"] is not None else None
        )

        return BookingListItemDto(
            id=row["id"],
            booking_uid=row["booking_uid"],
            first_seen_at=row["first_seen_at"],
            last_seen_at=row["last_seen_at"],
            start_time=row["start_time"],
            end_time=row["end_time"],
            current_status=row["current_status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            organizer_participant=organizer_participant,
            client_participant=client_participant,
        )

    @staticmethod
    def _map_prefixed_participant(row: RowMapping, prefix: str) -> ParticipantDto:
        return ParticipantDto(user_id=row[f"{prefix}_user_id"])

    @classmethod
    def _map_prefixed_participant_optional(
        cls,
        row: RowMapping,
        prefix: str,
    ) -> ParticipantDto | None:
        if row[f"{prefix}_user_id"] is None:
            return None
        return cls._map_prefixed_participant(row, prefix)

    @staticmethod
    def _map_future_bounced_row_to_dto(row: RowMapping) -> BookingFutureBouncedEmailItemDto:
        organizer_participant = (
            ParticipantDto(user_id=row["organizer_user_id"]) if row["organizer_user_id"] is not None else None
        )
        client_participant = (
            ParticipantDto(user_id=row["client_user_id"]) if row["client_user_id"] is not None else None
        )

        bounce_statuses_raw = row["email_bounce_statuses"] or []
        email_bounce_statuses = tuple(str(status) for status in bounce_statuses_raw)

        return BookingFutureBouncedEmailItemDto(
            id=row["id"],
            booking_uid=row["booking_uid"],
            start_date=row["start_date"],
            end_time=row["end_time"],
            current_status=row["current_status"],
            organizer_participant=organizer_participant,
            client_participant=client_participant,
            email_bounce_statuses=email_bounce_statuses,
        )
