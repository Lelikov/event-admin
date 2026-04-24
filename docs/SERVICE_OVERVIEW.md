# event-admin Service Overview

## Domain

Read-only administrative API over the PostgreSQL database owned and written by `event-saver`. Provides booking inspection, notification audit, and admin authentication for the `event-admin-frontend` React UI.

## Responsibilities

- Authenticate admin users via email + password + TOTP, issue JWTs (`routes.py:37-53`)
- Expose paginated read-only endpoints for bookings, notifications, meeting links, chat events, video events (`routes.py:61-105`)
- Enforce RBAC: all `/bookings/*` routes require the `admin` role (`routes.py:28`, `auth.py:60-63`)
- Serve as the sole backend for `event-admin-frontend`

## NOT Responsible For

- **Writing data** -- `SqlExecutor` exposes only `fetch_one` and `fetch_all`; no write methods (`adapters/sql.py:15-21`, `interfaces/sql.py:10-13`)
- **Database migrations** -- schema changes live in `event-saver/alembic/`; this service has no `alembic/` directory
- **User/contact management** -- handled by `event-users`
- **Event ingestion or processing** -- handled by `event-receiver` and `event-saver`

## Runtime Dependencies

| Dependency | Role | Connection |
|---|---|---|
| PostgreSQL | Data source (same DB instance as event-saver) | `POSTGRES_DSN` -- read-only by convention (write methods removed from interface) |
| `event-users` | User data source for `/api/users/*` proxy endpoints | `USERS_SERVICE_URL` (HTTP via httpx `AsyncClient`); authenticated with `USERS_SERVICE_API_TOKEN` |

No RabbitMQ or Redis dependencies.

## Key Environment Variables

| Variable | Required | Default | Description | Reference |
|---|---|---|---|---|
| `POSTGRES_DSN` | Yes | -- | PostgreSQL async connection string (e.g. `postgresql+asyncpg://...`) | `config.py:27` |
| `JWT_SECRET_KEY` | Yes | -- | HMAC secret for signing/verifying JWTs | `config.py:31` |
| `USERS_SERVICE_URL` | Yes | -- | Base URL of the `event-users` service (e.g. `http://event-users:8000`) | `config.py:35` |
| `USERS_SERVICE_API_TOKEN` | Yes | -- | Bearer token for authenticating requests to `event-users` | `config.py:36` |
| `CACHE_INVALIDATION_TOKEN` | Yes | -- | Bearer token that `event-users` sends when calling `POST /api/users/cache/invalidate` | `config.py:38` |
| `DEBUG` | No | `False` | When `True`, middleware bypasses JWT validation (development only) | `config.py:14`, `middleware.py:30-31` |
| `LOG_LEVEL` | No | `INFO` | Structlog level: DEBUG, INFO, WARNING, ERROR, CRITICAL | `config.py:15` |
| `CORS_ORIGINS` | No | `["http://localhost:5173"]` | Allowed CORS origins list | `config.py:29` |
| `JWT_ALGORITHM` | No | `HS256` | JWT signing algorithm | `config.py:32` |
| `JWT_EXPIRE_MINUTES` | No | `1440` (24h) | Token lifetime in minutes | `config.py:33` |
| `USERS_CACHE_TTL_SECONDS` | No | `300` | TTL for in-memory users cache entries | `config.py:37` |

## Layer Map

```
HTTP Request
    |
    v
routes.py              FastAPI route handlers; query param parsing, response schema conversion
    |                  (DishkaRoute injects dependencies)
    v
controllers/           Thin orchestration layer; delegates to DB adapter
    |
    v
adapters/              SQL query logic + RowMapping -> DTO mapping
    |                  bookings_db.py  -- booking queries
    |                  admin_users_db.py -- admin_users lookup
    v
adapters/sql.py        SqlExecutor wraps AsyncSession with text() queries
    |
    v
PostgreSQL             Shared DB (owned by event-saver)
```

**Supporting layers:**
- `interfaces/` -- Protocol-based contracts (`ISqlExecutor`, `IBookingsDBAdapter`, `IBookingsController`, `IAdminUsersDBAdapter`, `IPasswordService`, `ITOTPService`) -- `interfaces/*.py`
- `dto/` -- Frozen dataclasses for inter-layer data transfer -- `dto/bookings.py`
- `schemas/` -- Pydantic response models with `from_dto()` classmethods -- `schemas/bookings.py`, `schemas/auth.py`
- `ioc.py` -- Dishka DI provider; APP scope (engine, sessionmaker, settings) and REQUEST scope (session, executor, adapters, controller) -- `ioc.py:29-104`
- `middleware.py` -- `JWTAuthMiddleware` validates bearer tokens on non-public paths -- `middleware.py:14-47`
- `auth.py` -- Token creation, `get_current_user`, `require_admin` dependencies -- `auth.py:1-63`
- `services/` -- `PasswordService` (bcrypt), `TOTPService` (pyotp) -- `services/password.py`, `services/totp.py`

## DI Scopes (Dishka)

| Scope | Provided | Reference |
|---|---|---|
| APP | `Settings`, `AsyncEngine`, `async_sessionmaker`, `ISqlExecutorFactory`, `IPasswordService`, `ITOTPService` | `ioc.py:30-84` |
| REQUEST | `AsyncSession`, `ISqlExecutor`, `IAdminUsersDBAdapter`, `IBookingsDBAdapter`, `IBookingsController` | `ioc.py:67-97` |

## Known Limitations

1. **No test coverage** -- no `tests/` directory exists (`audit:LOW`)
2. **`admin_users` migration is inline SQL in a docstring** -- no Alembic migration file; schema changes require manual DDL (`db/models.py:14-26`)
3. **JWT default expiry is 24 hours** with no server-side revocation; `POST /auth/logout` is a no-op (`routes.py:70-76`, `config.py:33`)
4. **`DEBUG=True` bypasses all authentication** -- must never be set in production (`middleware.py:37-40`)

## Resolved (2026-04-21)

- ~~Login failures not logged~~ -- auth audit logging added with per-reason `login_failed` / `login_success` events (`routes.py:53-67`)
- ~~No request-id correlation~~ -- `X-Request-ID` header and structlog contextvars binding added (`middleware.py:32-33`)
- ~~Mutable list fields in frozen DTOs~~ -- verified all DTO collection fields already use `tuple[..., ...]` (`dto/bookings.py`)
- ~~Python 2 except syntax in middleware~~ -- fixed (`middleware.py:59`)
- ~~Settings re-instantiated per request in middleware~~ -- now injected via constructor (`middleware.py:24`)
- ~~Double JWT decode (middleware + dependency)~~ -- consolidated; middleware stores payload in `request.state` (`middleware.py:56`, `auth.py:35-42`)
- ~~CORS `allow_origins=["*"]`~~ -- now uses configurable `cors_origins` from Settings (`main.py:49`)
- ~~`BookingDetailsResponse` missing timestamp fields~~ -- `first_seen_at`, `last_seen_at`, `updated_at` added (`schemas/bookings.py:204-206,210`)
- ~~Dead logger suppressions~~ -- removed `aiokafka`, `asyncio_redis`, `urllib3`, `botocore` (`logger.py:72`)
