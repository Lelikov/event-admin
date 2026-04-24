# event-admin Dependencies

## Depends On

| Dependency | Type | Nature | Connection Details |
|---|---|---|---|
| PostgreSQL (event-saver's DB) | Database | Read-only by convention | `POSTGRES_DSN` env var; `asyncpg` driver; pool_size=10, max_overflow=20 (`ioc.py:45-50`) |
| `event-users` | HTTP service | Outbound proxy | `USERS_SERVICE_URL` env var; httpx `AsyncClient` (APP scope); `UsersClient` (`adapters/users_client.py`) proxies `/api/users/*` endpoints; responses cached in-process via `UsersCache` (TTL: `USERS_CACHE_TTL_SECONDS`, default 300s) |

No RabbitMQ or Redis dependencies.

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
- `POST /auth/login` -- obtain JWT
- `GET /bookings` -- paginated booking list with filters
- `GET /bookings/future-email-bounced` -- upcoming bookings with email delivery issues
- `GET /bookings/{booking_uid}` -- full booking detail with notifications, meetings, chat, video
- `POST /auth/logout` -- client-side logout signal (no-op server-side)

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
| `event-users` down or unreachable | `GET /api/users/*` and `POST /api/users/by-ids` return the upstream HTTP error; cached entries remain available until TTL expires | In-memory TTL cache (`UsersCache`) reduces blast radius; booking endpoints are unaffected |
| Invalid/missing `JWT_SECRET_KEY` | Tokens cannot be created or validated; effectively locked out | Required field with no default (`config.py:31`) -- app fails to start if missing |
| Invalid/missing `USERS_SERVICE_URL`, `USERS_SERVICE_API_TOKEN`, or `CACHE_INVALIDATION_TOKEN` | App fails to start | All three are required fields with no defaults (`config.py:35-38`) |
| `DEBUG=True` in production | All auth bypassed, full data exposure | Must be `False` in production; enforced by deployment policy |

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
| `ruff` | Linting/formatting (dev) |
| `pre-commit` | Git hooks (dev) |
