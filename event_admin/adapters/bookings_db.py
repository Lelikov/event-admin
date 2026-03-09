from typing import TYPE_CHECKING

from event_admin.dto.bookings import BookingListFiltersDto, BookingListItemDto, ParticipantDto
from event_admin.interfaces.bookings import IBookingsDBAdapter
from event_admin.interfaces.sql import ISqlExecutor


if TYPE_CHECKING:
    from sqlalchemy.engine import RowMapping


class BookingsDBAdapter(IBookingsDBAdapter):
    def __init__(self, sql_executor: ISqlExecutor) -> None:
        self.sql_executor = sql_executor

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
