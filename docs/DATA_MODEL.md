# event-admin Data Model

## Ownership

All tables (except `admin_users`) are **owned by `event-saver`**. Migrations live in `event-saver/alembic/`. This service connects read-only by convention -- `SqlExecutor` exposes only `fetch_one` and `fetch_all` (`adapters/sql.py:15-21`).

For the authoritative schema definition of event-saver-owned tables, see `event-saver/DATA_MODEL.md`.

---

## Tables Read

The following tables are queried by `event-admin` adapters:

| Table | Queried In | Purpose |
|---|---|---|
| `bookings` | `bookings_db.py:55-78, 83-101` | Core booking records |
| `booking_organizer_history` | `bookings_db.py:109-121` | Organizer assignment history per booking |
| `booking_meeting_links` | `bookings_db.py:124-138` | Meeting URLs associated with bookings |
| `booking_email_notifications` | `bookings_db.py:141-161` | Email notification records |
| `booking_email_status_history` | `bookings_db.py:166-180` | Delivery status history for each email notification |
| `booking_telegram_notifications` | `bookings_db.py:183-197` | Telegram notification records |
| `booking_chat_events` | `bookings_db.py:199-217` | Chat messages/events linked to bookings |
| `booking_video_events` | `bookings_db.py:219-233` | Jitsi/video call events linked to bookings |
| `admin_users` | `admin_users_db.py:16-19` | Admin panel credentials and roles |

---

## admin_users Table (event-admin owned)

Defined in `db/models.py` (`AdminUser`). The tracked, idempotent DDL lives in **`scripts/admin_users.sql`** (apply with `psql "$POSTGRES_DSN" -f scripts/admin_users.sql`). event-admin intentionally has no Alembic — event-saver owns the shared schema; `admin_users` is the single event-admin-owned table. A test (`tests/test_admin_users_ddl.py`) keeps the script in sync with the model.

```sql
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
```

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | UUID | No | `gen_random_uuid()` | PK |
| `email` | TEXT | No | -- | Unique; used as login identifier |
| `hashed_password` | TEXT | No | -- | bcrypt hash |
| `totp_secret` | TEXT | No | -- | Base32-encoded TOTP seed |
| `role` | TEXT | No | `'user'` | `'admin'` (full access) or `'user'` (read-only in future) |
| `is_active` | BOOLEAN | No | `TRUE` | Inactive users cannot log in |
| `created_at` | TIMESTAMPTZ | No | `NOW()` | Row creation time |
| `updated_at` | TIMESTAMPTZ | No | `NOW()` | Auto-updated on change |

**Indexes:** `ix_admin_users_email` on `email` (also covered by UNIQUE constraint).

**Queried by:** `AdminUsersDBAdapter.get_by_email()` (`adapters/admin_users_db.py:16-19`).

---

## Key SQL Queries in bookings_db.py

### list_bookings (`bookings_db.py:29-80`)

```sql
SELECT b.id, b.booking_uid, b.first_seen_at, b.last_seen_at,
       b.start_time, b.end_time, b.current_status,
       b.created_at, b.updated_at, b.organizer_user_id, b.client_user_id
FROM bookings b
[WHERE <dynamic filters using ANY(:param)>]
ORDER BY b.last_seen_at DESC
LIMIT :limit OFFSET :offset
```

Dynamic filters: `booking_uids`, `current_statuses`, `current_organizer_user_ids`, `current_client_user_ids`.

### get_booking_details (`bookings_db.py:82-357`)

1. Fetch single booking row by `booking_uid` (LIMIT 1)
2. Fetch `booking_organizer_history` by `booking_ref_id`, ordered by `effective_from DESC`
3. Fetch `booking_meeting_links` by `booking_ref_id`, ordered by `occurred_at DESC`
4. Fetch `booking_email_notifications` by `booking_ref_id`, ordered by `created_at DESC`
5. Fetch `booking_email_status_history` by `notification_ref_id = ANY(...)`, ordered by `status_event_time ASC`
6. Fetch `booking_telegram_notifications` by `booking_ref_id`, ordered by `sent_at DESC`
7. Fetch `booking_chat_events` by `booking_ref_id` (excluding `message.read` type), ordered by `occurred_at ASC`
8. Fetch `booking_video_events` by `booking_ref_id`, ordered by `event_time DESC`

All queries are sequential (7 round-trips per request).

### list_future_email_bounced_bookings (`bookings_db.py:359-393`)

```sql
SELECT b.id, b.booking_uid, b.start_time AS start_date, b.end_time,
       b.current_status, b.organizer_user_id, b.client_user_id,
       ARRAY_AGG(DISTINCT ben.last_status) FILTER (WHERE ben.last_status IN ('hard_bounce','soft_bounce'))
FROM bookings b
JOIN booking_email_notifications ben ON ben.booking_ref_id = b.id
WHERE b.start_time > now() AND ben.last_status IN ('hard_bounce', 'soft_bounce')
GROUP BY b.id, ...
ORDER BY b.start_time ASC, b.id ASC
LIMIT :limit OFFSET :offset
```

---

## Relationships Between Tables

```
bookings (PK: id, unique: booking_uid)
    |
    |-- booking_organizer_history.booking_ref_id -> bookings.id (CASCADE)
    |-- booking_meeting_links.booking_ref_id -> bookings.id (CASCADE)
    |-- booking_email_notifications.booking_ref_id -> bookings.id (CASCADE)
    |       |-- booking_email_status_history.notification_ref_id -> booking_email_notifications.id (CASCADE)
    |-- booking_telegram_notifications.booking_ref_id -> bookings.id (CASCADE)
    |-- booking_chat_events.booking_ref_id -> bookings.id (CASCADE)
    |-- booking_video_events.booking_ref_id -> bookings.id (CASCADE)

events (PK: event_id) -- referenced by source_event_id / raw_event_id FKs (SET NULL or CASCADE)
```

`user_id` columns in child tables reference UUIDs from `event-users` service (no FK constraint across services).
