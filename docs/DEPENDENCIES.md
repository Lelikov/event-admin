# event-admin Dependencies

## Depends On

| Dependency | Type | Nature | Connection Details |
|---|---|---|---|
| PostgreSQL (event-saver's DB) | Database | Read-only by convention | `POSTGRES_DSN` env var; `asyncpg` driver; pool_size=10, max_overflow=20 (`ioc.py:45-50`) |
| `event-users` | HTTP service | Outbound proxy | `USERS_SERVICE_URL` env var; httpx `AsyncClient` (APP scope); `UsersClient` (`adapters/users_client.py`) proxies `/api/users/*` endpoints (lookup via `GET /api/users/by-identity`); responses cached in-process via `UsersCache` (TTL: `USERS_CACHE_TTL_SECONDS`, default 300s) |
| `event-receiver` | HTTP service | Outbound CloudEvent publish | `EVENT_RECEIVER_URL` env var; `EventPublisherClient` posts binary-mode CloudEvents to `POST /event/admin` with `EVENT_RECEIVER_API_KEY` as the raw `Authorization` value; tenacity-retried on transport errors (`EVENT_PUBLISH_ATTEMPTS`, default 3), timeout `EVENT_PUBLISH_TIMEOUT_SECONDS` (default 10s) |

No direct RabbitMQ or Redis dependencies (events reach RabbitMQ via event-receiver).

### PostgreSQL Details

- Same physical database instance as `event-saver`
- Read-only enforced at application level: `ISqlExecutor` protocol exposes only `fetch_one` and `fetch_all` (`interfaces/sql.py:10-13`)
- `SqlExecutor` implementation has no `execute` or `execute_in_transaction` methods (`adapters/sql.py:11-21`)
- Recommendation from audit: use a dedicated read-only PostgreSQL role for defence-in-depth

---

## Provides To

| Consumer | Protocol | What It Provides |
|---|---|---|
| `event-admin-frontend` | HTTP REST (JSON) | Booking list/detail/bounced-email endpoints; admin login/logout |

The frontend calls:
- `POST /auth/login` -- obtain JWT (rate-limited; TOTP codes are single-use)
- `GET /bookings` -- paginated booking list with filters
- `GET /bookings/future-email-bounced` -- upcoming bookings with email delivery issues
- `GET /bookings/{booking_uid}` -- full booking detail with notifications, meetings, chat, video
- `POST /bookings/{booking_uid}/reassign-client` -- publish `booking.client_reassigned` (202)
- `GET/POST /api/users/*` -- typed proxy to event-users
- `POST /api/users/id/{user_id}/change-email` -- publish `user.email.change_requested` (202)
- `POST /auth/logout` -- client-side logout signal (no-op server-side)

`event-receiver` consumes the published CloudEvents and routes them:
`booking.client_reassigned` → `events.booking.lifecycle` (event-saver);
`user.email.change_requested` → `events.user.email` (event-users).

---

## What Breaks If event-admin Goes Down

| Affected Component | Impact | Severity |
|---|---|---|
| `event-admin-frontend` | Complete loss of admin UI functionality -- cannot view bookings, notifications, or log in | **CRITICAL** |
| `event-saver` | No impact -- continues writing to DB independently | None |
| `event-receiver` | No impact -- continues ingesting events | None |
| `event-users` | No impact -- independent service | None |

`event-admin` is a leaf service with no downstream dependents besides the frontend. Its unavailability does not affect event processing, data ingestion, or user management.

---

## Failure Modes

| Failure | Symptom | Mitigation |
|---|---|---|
| PostgreSQL connection pool exhausted | 500 errors on all endpoints | Pool pre-ping enabled (`ioc.py:49`); max 30 connections (10 + 20 overflow) |
| PostgreSQL down | 500 errors on all endpoints | Health check at `GET /health` does not probe DB (only returns static response) |
| `event-users` down or unreachable | `GET /api/users/*` and `POST /api/users/by-ids` return the upstream HTTP error; cached entries remain available until TTL expires; `change-email` / `reassign-client` fail pre-validation | In-memory TTL cache (`UsersCache`) reduces blast radius; booking endpoints are unaffected |
| `event-receiver` down, slow, or rejecting (e.g. wrong `EVENT_RECEIVER_API_KEY`) | `change-email` and `reassign-client` return **502** with `"the action was NOT applied"` after retries; the failed publish is logged with event type and upstream status. Read endpoints are unaffected | tenacity retries transport errors (`EVENT_PUBLISH_ATTEMPTS`); no outbox — the admin must retry the action manually |
| Invalid/missing `JWT_SECRET_KEY` | Tokens cannot be created or validated; effectively locked out | Required field with no default -- app fails to start if missing |
| Invalid/missing `USERS_SERVICE_URL`, `USERS_SERVICE_API_TOKEN`, `CACHE_INVALIDATION_TOKEN`, `EVENT_RECEIVER_URL`, or `EVENT_RECEIVER_API_KEY` | App fails to start | All are required fields with no defaults |
| Weak/placeholder secrets with `DEBUG=False` | App refuses to start (secret-strength validator) | Intentional fail-fast; generate real secrets per `.env.example` |
| `DEBUG=True` in production | No auth impact (bypass removed in audit-v2); secret-strength validation is skipped and logs render in console mode | Keep `False` in production so weak secrets are rejected at startup |

---

## Build/Dev Dependencies

Key Python packages (from `pyproject.toml`):

| Package | Purpose |
|---|---|
| `fastapi` | HTTP framework |
| `uvicorn` | ASGI server |
| `sqlalchemy[asyncio]` + `asyncpg` | Async PostgreSQL access |
| `dishka` | Dependency injection |
| `pyjwt` | JWT creation and validation |
| `bcrypt` | Password hashing (`services/password.py`) |
| `pyotp` | TOTP verification (`services/totp.py`) |
| `structlog` | Structured logging |
| `pydantic-settings` | Configuration from env vars |
| `cloudevents` | CloudEvents binary-mode encoding for event-receiver |
| `tenacity` | Retry policy for event publishing |
| `httpx` | Async HTTP client (event-users proxy, event-receiver publish) |
| `ruff` | Linting/formatting (dev) |
| `pre-commit` | Git hooks (dev) |
| `pytest` + `pytest-asyncio` | Test suite (dev) — `uv run pytest` |
