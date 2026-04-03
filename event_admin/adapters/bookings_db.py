from typing import TYPE_CHECKING

from event_admin.dto.bookings import (
    BookingChatEventItemDto,
    BookingDetailsDto,
    BookingEmailNotificationItemDto,
    BookingEmailStatusHistoryItemDto,
    BookingFutureBouncedEmailItemDto,
    BookingListFiltersDto,
    BookingListItemDto,
    BookingMeetingLinkItemDto,
    BookingOrganizerHistoryItemDto,
    BookingTelegramNotificationItemDto,
    BookingVideoEventItemDto,
    ParticipantDto,
    ParticipantListFiltersDto,
)
from event_admin.interfaces.bookings import IBookingsDBAdapter
from event_admin.interfaces.sql import ISqlExecutor


if TYPE_CHECKING:
    from sqlalchemy.engine import RowMapping


class BookingsDBAdapter(IBookingsDBAdapter):
    def __init__(self, sql_executor: ISqlExecutor) -> None:
        self.sql_executor = sql_executor

    async def list_participants(self, filters: ParticipantListFiltersDto) -> list[ParticipantDto]:
        conditions: list[str] = []
        values: dict = {}

        if filters.roles:
            conditions.append("p.role = ANY(:roles)")
            values["roles"] = filters.roles

        if filters.email is not None:
            conditions.append("p.email ILIKE :email")
            values["email"] = f"%{filters.email}%"

        query = """
            SELECT
                p.id,
                p.email,
                p.role,
                p.time_zone,
                p.created_at,
                p.updated_at
            FROM participants p
        """

        if conditions:
            query += "\nWHERE " + " AND ".join(conditions)

        query += "\nORDER BY p.id ASC"

        rows = await self.sql_executor.fetch_all(query, values)
        return [
            ParticipantDto(
                id=row["id"],
                email=row["email"],
                role=row["role"],
                time_zone=row["time_zone"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    async def list_bookings(self, filters: BookingListFiltersDto) -> list[BookingListItemDto]:
        conditions: list[str] = []
        values: dict[str, str | int] = {}

        if filters.booking_uids:
            conditions.append("b.booking_uid = ANY(:booking_uids)")
            values["booking_uids"] = filters.booking_uids

        if filters.current_statuses:
            conditions.append("b.current_status = ANY(:current_statuses)")
            values["current_statuses"] = filters.current_statuses

        if filters.current_organizer_participant_ref_ids:
            conditions.append(
                "b.current_organizer_participant_ref_id = ANY(:current_organizer_participant_ref_ids)",
            )
            values["current_organizer_participant_ref_ids"] = filters.current_organizer_participant_ref_ids

        if filters.current_client_participant_ref_ids:
            conditions.append(
                "b.current_client_participant_ref_id = ANY(:current_client_participant_ref_ids)",
            )
            values["current_client_participant_ref_ids"] = filters.current_client_participant_ref_ids
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

                op.id AS organizer_id,
                op.email AS organizer_email,
                op.role AS organizer_role,
                op.time_zone AS organizer_time_zone,
                op.created_at AS organizer_created_at,
                op.updated_at AS organizer_updated_at,

                cp.id AS client_id,
                cp.email AS client_email,
                cp.role AS client_role,
                cp.time_zone AS client_time_zone,
                cp.created_at AS client_created_at,
                cp.updated_at AS client_updated_at
            FROM bookings b
            LEFT JOIN participants op ON op.id = b.current_organizer_participant_ref_id
            LEFT JOIN participants cp ON cp.id = b.current_client_participant_ref_id
        """

        if where_clause:
            query += f"\n{where_clause}"

        query += """
            ORDER BY b.last_seen_at DESC
        """

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
                b.current_organizer_participant_ref_id,
                b.current_client_participant_ref_id,
                b.created_at,
                b.updated_at,

                op.id AS current_organizer_id,
                op.email AS current_organizer_email,
                op.role AS current_organizer_role,
                op.time_zone AS current_organizer_time_zone,
                op.created_at AS current_organizer_created_at,
                op.updated_at AS current_organizer_updated_at,

                cp.id AS current_client_id,
                cp.email AS current_client_email,
                cp.role AS current_client_role,
                cp.time_zone AS current_client_time_zone,
                cp.created_at AS current_client_created_at,
                cp.updated_at AS current_client_updated_at
            FROM bookings b
            LEFT JOIN participants op ON op.id = b.current_organizer_participant_ref_id
            LEFT JOIN participants cp ON cp.id = b.current_client_participant_ref_id
            WHERE b.booking_uid = :booking_uid
            LIMIT 1
            """,
            {"booking_uid": booking_uid},
        )

        if booking_row is None:
            return None

        booking_ref_id = booking_row["id"]

        organizer_history_rows = await self.sql_executor.fetch_all(
            """
            SELECT
                boh.id,
                boh.organizer_participant_ref_id,
                boh.source_event_id,
                boh.effective_from,
                boh.created_at,
                p.id AS participant_id,
                p.email AS participant_email,
                p.role AS participant_role,
                p.time_zone AS participant_time_zone,
                p.created_at AS participant_created_at,
                p.updated_at AS participant_updated_at
            FROM booking_organizer_history boh
            JOIN participants p ON p.id = boh.organizer_participant_ref_id
            WHERE boh.booking_ref_id = :booking_ref_id
            ORDER BY boh.effective_from DESC, boh.id DESC
            """,
            {"booking_ref_id": booking_ref_id},
        )

        meeting_link_rows = await self.sql_executor.fetch_all(
            """
            SELECT
                bml.id,
                bml.participant_ref_id,
                bml.meeting_url,
                bml.source_event_id,
                bml.occurred_at,
                bml.created_at,
                bml.updated_at,
                p.id AS participant_id,
                p.email AS participant_email,
                p.role AS participant_role,
                p.time_zone AS participant_time_zone,
                p.created_at AS participant_created_at,
                p.updated_at AS participant_updated_at
            FROM booking_meeting_links bml
            JOIN participants p ON p.id = bml.participant_ref_id
            WHERE bml.booking_ref_id = :booking_ref_id
            ORDER BY bml.occurred_at DESC, bml.id DESC
            """,
            {"booking_ref_id": booking_ref_id},
        )

        email_notification_rows = await self.sql_executor.fetch_all(
            """
            SELECT
                ben.id,
                ben.participant_ref_id,
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
                p.id AS participant_id,
                p.email AS participant_email,
                p.role AS participant_role,
                p.time_zone AS participant_time_zone,
                p.created_at AS participant_created_at,
                p.updated_at AS participant_updated_at
            FROM booking_email_notifications ben
            LEFT JOIN participants p ON p.id = ben.participant_ref_id
            WHERE ben.booking_ref_id = :booking_ref_id
            ORDER BY ben.created_at DESC, ben.id DESC
            """,
            {"booking_ref_id": booking_ref_id},
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

        telegram_notification_rows = await self.sql_executor.fetch_all(
            """
            SELECT
                btn.id,
                btn.participant_ref_id,
                btn.trigger_event,
                btn.source_event_id,
                btn.sent_at,
                btn.created_at,
                p.id AS participant_id,
                p.email AS participant_email,
                p.role AS participant_role,
                p.time_zone AS participant_time_zone,
                p.created_at AS participant_created_at,
                p.updated_at AS participant_updated_at
            FROM booking_telegram_notifications btn
            LEFT JOIN participants p ON p.id = btn.participant_ref_id
            WHERE btn.booking_ref_id = :booking_ref_id
            ORDER BY btn.sent_at DESC, btn.id DESC
            """,
            {"booking_ref_id": booking_ref_id},
        )

        chat_event_rows = await self.sql_executor.fetch_all(
            """
            SELECT
                bce.id,
                bce.raw_event_id,
                bce.provider,
                bce.chat_event_type,
                bce.message_id,
                bce.participant_ref_id,
                bce.is_read,
                bce.text_preview,
                bce.occurred_at,
                bce.updated_at,
                p.id AS participant_id,
                p.email AS participant_email,
                p.role AS participant_role,
                p.time_zone AS participant_time_zone,
                p.created_at AS participant_created_at,
                p.updated_at AS participant_updated_at
            FROM booking_chat_events bce
            LEFT JOIN participants p ON p.id = bce.participant_ref_id
            WHERE bce.booking_ref_id = :booking_ref_id AND bce.chat_event_type != 'message.read'
            ORDER BY bce.occurred_at ASC
            """,
            {"booking_ref_id": booking_ref_id},
        )

        video_event_rows = await self.sql_executor.fetch_all(
            """
            SELECT
                bve.id,
                bve.raw_event_id,
                bve.video_event_type,
                bve.participant_role,
                bve.participant_ref_id,
                bve.event_time,
                bve.payload,
                p.id AS participant_id,
                p.email AS participant_email,
                p.role AS participant_role,
                p.time_zone AS participant_time_zone,
                p.created_at AS participant_created_at,
                p.updated_at AS participant_updated_at
            FROM booking_video_events bve
            LEFT JOIN participants p ON p.id = bve.participant_ref_id
            WHERE bve.booking_ref_id = :booking_ref_id
            ORDER BY bve.event_time DESC NULLS LAST, bve.id DESC
            """,
            {"booking_ref_id": booking_ref_id},
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

        organizer_history = [
            BookingOrganizerHistoryItemDto(
                id=row["id"],
                organizer_participant_ref_id=row["organizer_participant_ref_id"],
                organizer_participant=self._map_prefixed_participant(row, "participant"),
                source_event_id=row["source_event_id"],
                effective_from=row["effective_from"],
                created_at=row["created_at"],
            )
            for row in organizer_history_rows
        ]

        meeting_links = [
            BookingMeetingLinkItemDto(
                id=row["id"],
                participant_ref_id=row["participant_ref_id"],
                participant=self._map_prefixed_participant(row, "participant"),
                meeting_url=row["meeting_url"],
                source_event_id=row["source_event_id"],
                occurred_at=row["occurred_at"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in meeting_link_rows
        ]

        email_notifications = [
            BookingEmailNotificationItemDto(
                id=row["id"],
                participant_ref_id=row["participant_ref_id"],
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
                status_history=status_history_by_notification.get(row["id"], []),
            )
            for row in email_notification_rows
        ]

        telegram_notifications = [
            BookingTelegramNotificationItemDto(
                id=row["id"],
                participant_ref_id=row["participant_ref_id"],
                participant=self._map_prefixed_participant_optional(row, "participant"),
                trigger_event=row["trigger_event"],
                source_event_id=row["source_event_id"],
                sent_at=row["sent_at"],
                created_at=row["created_at"],
            )
            for row in telegram_notification_rows
        ]

        chat_events = [
            BookingChatEventItemDto(
                id=row["id"],
                raw_event_id=row["raw_event_id"],
                provider=row["provider"],
                chat_event_type=row["chat_event_type"],
                message_id=row["message_id"],
                participant_ref_id=row["participant_ref_id"],
                participant=self._map_prefixed_participant_optional(row, "participant"),
                is_read=row["is_read"],
                text_preview=row["text_preview"],
                occurred_at=row["occurred_at"],
                updated_at=row["updated_at"],
            )
            for row in chat_event_rows
        ]

        video_events = [
            BookingVideoEventItemDto(
                id=row["id"],
                raw_event_id=row["raw_event_id"],
                video_event_type=row["video_event_type"],
                participant_role=row["participant_role"],
                participant_ref_id=row["participant_ref_id"],
                participant=self._map_prefixed_participant_optional(row, "participant"),
                event_time=row["event_time"],
                payload=row["payload"],
            )
            for row in video_event_rows
        ]

        return BookingDetailsDto(
            id=booking_row["id"],
            booking_uid=booking_row["booking_uid"],
            first_seen_at=booking_row["first_seen_at"],
            last_seen_at=booking_row["last_seen_at"],
            start_time=booking_row["start_time"],
            end_time=booking_row["end_time"],
            current_status=booking_row["current_status"],
            current_organizer_participant_ref_id=booking_row["current_organizer_participant_ref_id"],
            current_client_participant_ref_id=booking_row["current_client_participant_ref_id"],
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
        )

    async def list_future_email_bounced_bookings(self) -> list[BookingFutureBouncedEmailItemDto]:
        rows = await self.sql_executor.fetch_all(
            """
            SELECT
                b.id,
                b.booking_uid,
                b.start_time AS start_date,
                b.end_time,
                b.current_status,
                op.id AS organizer_id,
                op.email AS organizer_email,
                op.role AS organizer_role,
                op.time_zone AS organizer_time_zone,
                op.created_at AS organizer_created_at,
                op.updated_at AS organizer_updated_at,
                cp.id AS client_id,
                cp.email AS client_email,
                cp.role AS client_role,
                cp.time_zone AS client_time_zone,
                cp.created_at AS client_created_at,
                cp.updated_at AS client_updated_at,
                ARRAY_AGG(DISTINCT ben.last_status) FILTER (
                    WHERE ben.last_status IN ('hard_bounced', 'soft_bounced')
                ) AS email_bounce_statuses
            FROM bookings b
            JOIN booking_email_notifications ben ON ben.booking_ref_id = b.id
            LEFT JOIN participants op ON op.id = b.current_organizer_participant_ref_id
            LEFT JOIN participants cp ON cp.id = b.current_client_participant_ref_id
            WHERE b.start_time > now()
              AND ben.last_status IN ('hard_bounced', 'soft_bounced')
            GROUP BY
                b.id,
                b.booking_uid,
                b.start_time,
                b.end_time,
                b.current_status,
                op.id,
                op.email,
                op.role,
                op.time_zone,
                op.created_at,
                op.updated_at,
                cp.id,
                cp.email,
                cp.role,
                cp.time_zone,
                cp.created_at,
                cp.updated_at
            ORDER BY b.start_time ASC, b.id ASC
            """,
            {},
        )

        return [self._map_future_bounced_row_to_dto(row) for row in rows]

    @staticmethod
    def _map_row_to_dto(row: RowMapping) -> BookingListItemDto:
        organizer_participant = None
        if row["organizer_id"] is not None:
            organizer_participant = ParticipantDto(
                id=row["organizer_id"],
                email=row["organizer_email"],
                role=row["organizer_role"],
                time_zone=row["organizer_time_zone"],
                created_at=row["organizer_created_at"],
                updated_at=row["organizer_updated_at"],
            )

        client_participant = None
        if row["client_id"] is not None:
            client_participant = ParticipantDto(
                id=row["client_id"],
                email=row["client_email"],
                role=row["client_role"],
                time_zone=row["client_time_zone"],
                created_at=row["client_created_at"],
                updated_at=row["client_updated_at"],
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
        return ParticipantDto(
            id=row[f"{prefix}_id"],
            email=row[f"{prefix}_email"],
            role=row[f"{prefix}_role"],
            time_zone=row[f"{prefix}_time_zone"],
            created_at=row[f"{prefix}_created_at"],
            updated_at=row[f"{prefix}_updated_at"],
        )

    @classmethod
    def _map_prefixed_participant_optional(
        cls,
        row: RowMapping,
        prefix: str,
    ) -> ParticipantDto | None:
        if row[f"{prefix}_id"] is None:
            return None
        return cls._map_prefixed_participant(row, prefix)

    @staticmethod
    def _map_future_bounced_row_to_dto(row: RowMapping) -> BookingFutureBouncedEmailItemDto:
        organizer_participant = None
        if row["organizer_id"] is not None:
            organizer_participant = ParticipantDto(
                id=row["organizer_id"],
                email=row["organizer_email"],
                role=row["organizer_role"],
                time_zone=row["organizer_time_zone"],
                created_at=row["organizer_created_at"],
                updated_at=row["organizer_updated_at"],
            )

        client_participant = None
        if row["client_id"] is not None:
            client_participant = ParticipantDto(
                id=row["client_id"],
                email=row["client_email"],
                role=row["client_role"],
                time_zone=row["client_time_zone"],
                created_at=row["client_created_at"],
                updated_at=row["client_updated_at"],
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
