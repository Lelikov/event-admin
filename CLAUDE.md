# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Run the server:**
```bash
uvicorn event_admin.main:app --reload
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

**Configuration:** Requires a `.env` file. Required vars: `POSTGRES_DSN`, `JWT_SECRET_KEY`, `USERS_SERVICE_URL`, `USERS_SERVICE_API_TOKEN`, `CACHE_INVALIDATION_TOKEN`. Optional: `DEBUG`, `LOG_LEVEL`, `CORS_ORIGINS`, `JWT_ALGORITHM`, `JWT_EXPIRE_MINUTES`, `USERS_CACHE_TTL_SECONDS`.

## Service role in the system

This service is a **read-only API** on top of the database owned and written by **event-saver** (`~/PycharmProjects/event-saver`).

```
event-receiver → RabbitMQ → event-saver (writes DB) ← event-admin (reads DB, exposes API)
                                                      ← event-users (separate users DB)
```

- **`event-saver`** — consumes RabbitMQ, writes all tables (`bookings`, `participants`, `events`, etc.)
- **`event-users`** — separate service managing users; `participants.user_id` references its UUID PK
- **Database migrations** live in **`event-saver/alembic/`** — never create migrations here

## Architecture

Layered async FastAPI service for reading booking data from PostgreSQL.

**Request flow:** `routes.py` → `controllers/` → `adapters/` → `adapters/sql.py` (SqlExecutor) → SQLAlchemy AsyncSession → PostgreSQL

**Key layers:**

- **`routes.py`** — FastAPI route handlers; convert query params/path params into DTOs, call controller via DI, convert result DTO to Pydantic response schema via `from_dto()`
- **`controllers/`** — Thin business logic layer; currently delegates directly to DB adapters
- **`adapters/bookings_db.py`** — All SQL query logic; executes multiple raw SQL queries per request and maps `RowMapping` results to DTOs
- **`adapters/admin_users_db.py`** — `AdminUsersDBAdapter`; fetches admin user rows by email for login
- **`adapters/sql.py`** — `SqlExecutor` wraps `AsyncSession` with `text()` queries; used by all DB adapters
- **`adapters/users_client.py`** — `UsersClient`; httpx-based proxy to `event-users` service; caches responses via `UsersCache`
- **`interfaces/`** — Protocol-based interfaces: `ISqlExecutor`, `ISqlExecutorFactory`, `IBookingsDBAdapter`, `IBookingsController`, `IAdminUsersDBAdapter`, `IPasswordService`, `ITOTPService`, `IUsersClient`
- **`services/password.py`** — `PasswordService`; bcrypt password verification (`IPasswordService`)
- **`services/totp.py`** — `TOTPService`; TOTP code verification via pyotp (`ITOTPService`)
- **`services/users_cache.py`** — `UsersCache`; in-memory TTL cache for user and list responses from `event-users`
- **`dto/`** — Frozen dataclasses for inter-layer communication
- **`schemas/auth.py`** — Pydantic models for login request/response
- **`schemas/bookings.py`** — Pydantic models for booking responses with `from_dto()` classmethods
- **`middleware.py`** — `JWTAuthMiddleware`; validates Bearer tokens, binds request-id to structlog context
- **`auth.py`** — `create_access_token`, `get_current_user`, `require_admin` FastAPI dependencies
- **`ioc.py`** — Dishka DI container; app-scoped and request-scoped providers
- **`db/models.py`** — SQLAlchemy ORM models (used for schema reference; queries are written as raw SQL in adapters)

**DI scopes:**
- `APP` scope: `Settings`, `AsyncEngine`, `async_sessionmaker`, `ISqlExecutorFactory`, `IPasswordService`, `ITOTPService`, `UsersCache`, `AsyncClient` (httpx), `IUsersClient`
- `REQUEST` scope: `AsyncSession`, `ISqlExecutor`, `IAdminUsersDBAdapter`, `IBookingsDBAdapter`, `IBookingsController`

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
