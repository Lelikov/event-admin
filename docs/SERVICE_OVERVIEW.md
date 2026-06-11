# event-admin Service Overview

## Domain

Administrative API for the `event-admin-frontend` React UI. **Reads** are served directly from the PostgreSQL database owned and written by `event-saver` (bookings, notifications, meeting links, chat/video events). **Writes never touch the database**: the two mutation endpoints (client email change, booking client reassignment) publish CloudEvents to `event-receiver`, which routes them through RabbitMQ to the owning services.

## Responsibilities

- Authenticate admin users via email + password + TOTP, issue JWTs (`routes.py`)
- Enforce brute-force lockout and TOTP single-use on login (`services/login_guard.py`)
- Expose paginated read-only endpoints for bookings, notifications, meeting links, chat events, video events
- Proxy `/api/users/*` reads to `event-users` through typed allowlist response models (`schemas/users_proxy.py`)
- Publish `user.email.change_requested` and `booking.client_reassigned` CloudEvents to `event-receiver` (`adapters/event_publisher.py`)
- Enforce RBAC: all `/bookings/*` and `/api/users/*` routes require the `admin` role

## NOT Responsible For

- **Writing to the database** — `SqlExecutor` exposes only `fetch_one`/`fetch_all`; mutations go out as CloudEvents and are applied by `event-users` / `event-saver`
- **Database migrations** — `event-saver/alembic/` owns the shared schema. The single exception is the event-admin-owned `admin_users` table, whose tracked DDL lives in `scripts/admin_users.sql`
- **User/contact management** — handled by `event-users`
- **Direct RabbitMQ access** — events go through `event-receiver`'s HTTP ingress (`POST /event/admin`), never straight to the broker

## Runtime Dependencies

| Dependency | Role | Connection |
|---|---|---|
| PostgreSQL | Data source (same DB instance as event-saver) | `POSTGRES_DSN` — read-only by convention (no write methods in the interface) |
| `event-users` | User data source for `/api/users/*` proxy endpoints | `USERS_SERVICE_URL` (httpx); authenticated with `USERS_SERVICE_API_TOKEN` |
| `event-receiver` | CloudEvent ingress for the two mutation endpoints | `EVENT_RECEIVER_URL` (httpx); authenticated with `Authorization: Bearer {EVENT_RECEIVER_API_KEY}` (token compared constant-time on the receiver) |

No direct RabbitMQ or Redis dependencies.

## Key Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `POSTGRES_DSN` | Yes | — | PostgreSQL async connection string (`postgresql+asyncpg://...`) |
| `JWT_SECRET_KEY` | Yes | — | HMAC secret for JWTs (shared with `event-users`); ≥16 chars, non-placeholder outside DEBUG |
| `USERS_SERVICE_URL` | Yes | — | Base URL of `event-users` |
| `USERS_SERVICE_API_TOKEN` | Yes | — | Bearer token for `event-users` calls |
| `CACHE_INVALIDATION_TOKEN` | Yes | — | Shared secret `event-users` sends to `POST /api/users/cache/invalidate` |
| `EVENT_RECEIVER_URL` | Yes | — | Base URL of `event-receiver` (CloudEvent ingress) |
| `EVENT_RECEIVER_API_KEY` | Yes | — | Static key for `POST /event/admin`; must match receiver's `ADMIN_API_KEY` |
| `DEBUG` | No | `False` | Console log rendering + relaxes secret-strength validation. **Does NOT affect authentication** (the old auth bypass was removed in audit-v2) |
| `LOG_LEVEL` | No | `INFO` | Structlog level |
| `CORS_ORIGINS` | No | `["http://localhost:5173"]` | Allowed CORS origins (non-credentialed; GET/POST/OPTIONS only) |
| `JWT_ALGORITHM` | No | `HS256` | JWT signing algorithm |
| `JWT_EXPIRE_MINUTES` | No | `60` | Token lifetime in minutes |
| `JWT_AUDIENCE` / `JWT_ISSUER` | No | unset | Optional aud/iss claim binding (must match `event-users`; tolerant rollout when unset) |
| `USERS_CACHE_TTL_SECONDS` | No | `300` | TTL for in-memory users cache entries |
| `EVENT_PUBLISH_ATTEMPTS` | No | `3` | Retries for transport errors when publishing to event-receiver |
| `EVENT_PUBLISH_TIMEOUT_SECONDS` | No | `10` | httpx timeout for event publishing |
| `LOGIN_MAX_FAILURES` | No | `5` | Failed logins per IP+email before lockout |
| `LOGIN_LOCKOUT_SECONDS` | No | `300` | Lockout window length |

See `.env.example` for a template. Outside `DEBUG=True` the service **refuses to start** if any secret is shorter than 16 characters or a known placeholder.

## Layer Map

```
HTTP Request
    |
    v
middleware.py          JWTAuthMiddleware (always enforced; optional aud/iss binding)
    |
    v
routes.py              FastAPI route handlers (DishkaRoute DI)
    |                       |                        |
    v                       v                        v
controllers/           adapters/users_client.py  adapters/event_publisher.py
    |                  (httpx -> event-users,    (httpx -> event-receiver,
    v                   UsersCache TTL cache)     tenacity retries,
adapters/bookings_db.py                           EventPublishError -> 502)
adapters/admin_users_db.py
    |
    v
adapters/sql.py        SqlExecutor (read-only fetch_one/fetch_all, sequential per request session)
    |
    v
PostgreSQL             Shared DB (owned by event-saver)
```

**Supporting layers:**
- `interfaces/` — Protocol contracts (`ISqlExecutor`, `IBookingsDBAdapter`, `IBookingsController`, `IAdminUsersDBAdapter`, `IPasswordService`, `ITOTPService`, `IUsersClient`, `IEventPublisher`)
- `dto/` — frozen dataclasses; `schemas/` — Pydantic response models (`from_dto()`), typed users-proxy allowlist models
- `services/` — `PasswordService` (bcrypt), `TOTPService` (pyotp, fails closed on malformed secrets), `LoginGuard` (lockout + TOTP replay), `UsersCache`
- `errors.py` — `EventPublishError` (mapped to 502 by an app-level exception handler)
- `main.py` — `create_app()` factory: single `Settings` instance for DI, middleware, and CORS; explicit middleware ordering (CORS added last = outermost)
- `ioc.py` — Dishka provider, receives `Settings` from the factory

## DI Scopes (Dishka)

| Scope | Provided |
|---|---|
| APP | `Settings`, `AsyncEngine`, `async_sessionmaker`, `ISqlExecutorFactory`, `IPasswordService`, `ITOTPService`, `LoginGuard`, `UsersCache`, `AsyncClient` (users + receiver), `IUsersClient`, `IEventPublisher` |
| REQUEST | `AsyncSession`, `ISqlExecutor`, `IAdminUsersDBAdapter`, `IBookingsDBAdapter`, `IBookingsController` |

## Important Behavior Notes

1. **`get_booking_details` runs its 7 child-table queries sequentially** — they share one request-scoped `AsyncSession`, which forbids concurrent operations. Do not "optimize" with `asyncio.gather` (regression-tested in `tests/test_bookings_db.py`).
2. **Mutations are fire-and-acknowledge**: `change-email` and `reassign-client` return `202 Accepted` after the CloudEvent is accepted by event-receiver. If publishing fails, the client receives `502` with "the action was NOT applied".
3. **In-memory state** (`LoginGuard`, `UsersCache`) is per-process; multi-replica deployments need a shared store for lockout/replay tracking to be global.

## Known Limitations

1. **No server-side JWT revocation** — `POST /auth/logout` is a documented client-side no-op; lifetime is 60 min by default.
2. **LoginGuard / TOTP replay tracking is per-process** (see note above).
3. **TOCTOU on change-email uniqueness pre-check** — by design; `event-users` re-validates on consume.

## Resolved (audit-v2, 2026-06-11)

See `docs/AUDIT.md` for the full list: DEBUG auth bypass removed; `get_booking_details` gather bug fixed; publish error handling + retries; reassign-client booking validation; login lockout + TOTP replay protection; JWT 60-min default + aud/iss support; typed users-proxy models; constant-time cache token comparison; tracked `admin_users` DDL; test suite (75+ tests).
