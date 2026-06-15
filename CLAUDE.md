# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Run the server:**
```bash
uvicorn event_admin.main:app --reload
```

**Tests:**
```bash
uv run pytest
```

**Lint and format:**
```bash
ruff check .
ruff format .
```

**Pre-commit hooks:**
```bash
pre-commit run --all-files
```

**Configuration:** Requires a `.env` file (see `.env.example`). Required vars: `POSTGRES_DSN`, `JWT_SECRET_KEY`, `USERS_SERVICE_URL`, `USERS_SERVICE_API_TOKEN`, `CACHE_INVALIDATION_TOKEN`, `BLACKLIST_SERVICE_TOKEN`, `EVENT_RECEIVER_URL`, `EVENT_RECEIVER_API_KEY`, `NOTIFIER_SERVICE_URL`, `NOTIFIER_ADMIN_TOKEN`. Optional: `DEBUG`, `LOG_LEVEL`, `CORS_ORIGINS`, `JWT_ALGORITHM`, `JWT_EXPIRE_MINUTES`, `JWT_AUDIENCE`, `JWT_ISSUER`, `USERS_CACHE_TTL_SECONDS`, `EVENT_PUBLISH_ATTEMPTS`, `EVENT_PUBLISH_TIMEOUT_SECONDS`, `LOGIN_MAX_FAILURES`, `LOGIN_LOCKOUT_SECONDS`. Outside `DEBUG=True`, secrets must be ≥16 chars and non-placeholder (startup fails fast). `DEBUG` never affects authentication.

## Service role in the system

This service **reads** from the database owned and written by **event-saver** and **publishes mutation CloudEvents** to **event-receiver**. It never writes booking data itself; sanctioned direct-write exceptions are the admin-owned tables `admin_users` and `blacklist_entries` (`/api/blacklist` CRUD; `GET /api/blacklist/active` serves the currently-effective set to event-booking under the static `BLACKLIST_SERVICE_TOKEN`).

```
event-receiver → RabbitMQ → event-saver (writes DB) ← event-admin (reads DB, exposes API)
      ▲                                               ← event-users (separate users DB)
      └── event-admin POST /event/admin (user.email.change_requested, booking.client_reassigned)
```

- **`event-saver`** — consumes RabbitMQ, writes all tables (`bookings`, `participants`, `events`, etc.)
- **`event-users`** — separate service managing users; `participants.user_id` references its UUID PK
- **Database migrations** live in **`event-saver/alembic/`** — never create migrations here. The single event-admin-owned table (`admin_users`) has tracked DDL in `scripts/admin_users.sql`
- **Writes** go out as CloudEvents via `EventPublisherClient` → event-receiver `POST /event/admin`; publish failures map to 502 (`EventPublishError`)

### Notifications proxy

`/api/notifications/*` endpoints (require_admin) forward requests to the `event-notifier`
admin API and return the response. The service token (`NOTIFIER_ADMIN_TOKEN`) must match the
value configured in `event-notifier`. The proxy mirrors the pattern used for `event-users`:
an `INotifierClient` protocol, a `NotifierClient` httpx adapter (`NOTIFIER_SERVICE_URL`),
and a `_notifier_proxy_error` error mapper in `routes.py`. The admin-frontend "Уведомления"
page is the only caller.

The binding PUT path carries `recipient_role` between trigger and channel:
`PUT /api/notifications/config/{trigger_event}/{recipient_role}/{channel}` (proxied verbatim
to event-notifier; `recipient_role` must be `client` or `organizer` — notifier returns 400
`unknown role` otherwise).

## Architecture

Layered async FastAPI service for reading booking data from PostgreSQL.

**Request flow:** `routes.py` → `controllers/` → `adapters/` → `adapters/sql.py` (SqlExecutor) → SQLAlchemy AsyncSession → PostgreSQL

**Key layers:**

- **`routes.py`** — FastAPI route handlers; convert query params/path params into DTOs, call controller via DI, convert result DTO to Pydantic response schema via `from_dto()`
- **`controllers/`** — Thin business logic layer; currently delegates directly to DB adapters
- **`adapters/bookings_db.py`** — All SQL query logic; executes multiple raw SQL queries per request and maps `RowMapping` results to DTOs
- **`adapters/admin_users_db.py`** — `AdminUsersDBAdapter`; fetches admin user rows by email for login
- **`adapters/sql.py`** — `SqlExecutor` wraps `AsyncSession` with `text()` queries; used by all DB adapters
- **`adapters/users_client.py`** — `UsersClient`; httpx-based proxy to `event-users` service (lookup via `GET /api/users/by-identity`); caches responses via `UsersCache`
- **`adapters/notifier_client.py`** — `NotifierClient`; httpx-based proxy to `event-notifier` admin API (`NOTIFIER_SERVICE_URL`); sends `Authorization: Bearer <NOTIFIER_ADMIN_TOKEN>`; implements `INotifierClient` protocol (`interfaces/notifier.py`)
- **`adapters/event_publisher.py`** — `EventPublisherClient`; publishes binary-mode CloudEvents to event-receiver `POST /event/admin` with tenacity retries; raises `EventPublishError` (mapped to 502)
- **`interfaces/`** — Protocol-based interfaces: `ISqlExecutor`, `ISqlExecutorFactory`, `IBookingsDBAdapter`, `IBookingsController`, `IAdminUsersDBAdapter`, `IPasswordService`, `ITOTPService`, `IUsersClient`, `IEventPublisher`, `INotifierClient`
- **`services/password.py`** — `PasswordService`; bcrypt password verification (`IPasswordService`)
- **`services/totp.py`** — `TOTPService`; TOTP verification via pyotp (`ITOTPService`); fails closed on malformed secrets
- **`services/login_guard.py`** — `LoginGuard`; in-memory login lockout (per IP+email) and TOTP single-use tracking
- **`services/users_cache.py`** — `UsersCache`; in-memory TTL cache for user and list responses from `event-users`
- **`dto/`** — Frozen dataclasses for inter-layer communication
- **`schemas/auth.py`** — Pydantic models for login request/response
- **`schemas/bookings.py`** — Pydantic models for booking responses with `from_dto()` classmethods
- **`schemas/users_proxy.py`** — typed allowlist models for `/api/users/*` proxy responses (unknown upstream fields are dropped)
- **`middleware.py`** — `JWTAuthMiddleware`; validates Bearer tokens (always — no debug bypass), optional aud/iss binding, binds request-id to structlog context
- **`metrics.py`** — Prometheus metrics: HTTP RED middleware (`http_requests_total`, `http_request_duration_seconds` by route template; `/metrics` + `/health` excluded), `admin_logins_total{outcome}`, `admin_blacklist_ops_total{op}`; exposed at public `GET /metrics`
- **`auth.py`** — `create_access_token(settings, ...)`, `get_current_user`, `require_admin` FastAPI dependencies
- **`errors.py`** — `EventPublishError` domain error + `http_error()` helper: ALL error responses use structured `detail = {"code": "<stable_snake_case>", "message": "<human text>"}` (codes are a stable contract for the frontend; see `docs/API_CONTRACTS.md` § Common Error Responses)
- **`main.py`** — `create_app()` factory (single Settings path; CORS middleware added last = outermost, do not reorder)
- **`ioc.py`** — Dishka DI provider (`AppProvider(settings)`); app-scoped and request-scoped providers
- **`db/models.py`** — SQLAlchemy ORM models (schema reference only; `admin_users` DDL is tracked in `scripts/admin_users.sql`)

**DI scopes:**
- `APP` scope: `Settings`, `AsyncEngine`, `async_sessionmaker`, `ISqlExecutorFactory`, `IPasswordService`, `ITOTPService`, `LoginGuard`, `UsersCache`, `AsyncClient` (httpx), `IUsersClient`, `IEventPublisher`, `INotifierClient`
- `REQUEST` scope: `AsyncSession`, `ISqlExecutor`, `IAdminUsersDBAdapter`, `IBookingsDBAdapter`, `IBookingsController`

**Concurrency rule:** never `asyncio.gather` multiple queries on the request-scoped `SqlExecutor` — the shared `AsyncSession` forbids concurrent operations (regression-tested).

**Testing:** `tests/conftest.py` builds the app via `create_app(settings, provider=FakeProvider(...))` — no real DB or network. Every new endpoint/fix needs a test.

**Adding a new endpoint:** define route in `routes.py` → add method to `IBookingsController` and `IBookingsDBAdapter` protocols → implement in `BookingsController` and `BookingsDBAdapter` → add DTO in `dto/bookings.py` → add response schema in `schemas/bookings.py`.

## Service Documentation

- `docs/SERVICE_OVERVIEW.md` — architecture, maturity, known issues
- `docs/API_CONTRACTS.md` — HTTP endpoints, request/response schemas
- `docs/DATA_MODEL.md` — database tables (read-only view of event-saver's DB)
- `docs/DEPENDENCIES.md` — external service dependencies and failure modes
- `docs/AUDIT.md` — audit findings for this service

Cross-service architecture docs (message contracts, system topology, onboarding) are in `../docs/`.

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
|------|----------|
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
