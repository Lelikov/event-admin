-- admin_users: the ONLY table owned by event-admin.
--
-- Ownership note: every other table in this database (bookings, events,
-- booking_* projections) is owned and migrated by event-saver
-- (event-saver/alembic/). event-admin reads them and must never migrate
-- them. admin_users is event-admin-specific (panel logins), so its DDL is
-- tracked here instead of an untracked model docstring.
--
-- Apply (idempotent):
--   psql "$POSTGRES_DSN" -f scripts/admin_users.sql

CREATE TABLE IF NOT EXISTS admin_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    totp_secret TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_admin_users_email ON admin_users (email);
