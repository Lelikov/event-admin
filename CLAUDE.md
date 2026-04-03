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

**Configuration:** Requires a `.env` file with `POSTGRES_DSN` (PostgreSQL connection string). Optional: `DEBUG`, `LOG_LEVEL`.

## Architecture

Layered async FastAPI service for reading booking data from PostgreSQL.

**Request flow:** `routes.py` → `controllers/` → `adapters/` → `adapters/sql.py` (SqlExecutor) → SQLAlchemy AsyncSession → PostgreSQL

**Key layers:**

- **`routes.py`** — FastAPI route handlers; convert query params/path params into DTOs, call controller via DI, convert result DTO to Pydantic response schema via `from_dto()`
- **`controllers/`** — Thin business logic layer; currently delegates directly to DB adapters
- **`adapters/bookings_db.py`** — All SQL query logic; executes multiple raw SQL queries per request and maps `RowMapping` results to DTOs
- **`adapters/sql.py`** — `SqlExecutor` wraps `AsyncSession` with `text()` queries; used by all DB adapters
- **`interfaces/`** — Protocol-based interfaces (`ISqlExecutor`, `IBookingsDBAdapter`, `IBookingsController`) enabling loose coupling
- **`dto/`** — Frozen dataclasses for inter-layer communication
- **`schemas/`** — Pydantic models for HTTP responses with `from_dto()` classmethods
- **`ioc.py`** — Dishka DI container; app-scoped (engine, session factory, settings) and request-scoped (session, executor, adapter, controller)
- **`db/models.py`** — SQLAlchemy ORM models (used for schema reference; queries are written as raw SQL in adapters)

**DI scopes:**
- `APP` scope: `Settings`, `AsyncEngine`, `async_sessionmaker`, `ISqlExecutorFactory`
- `REQUEST` scope: `AsyncSession`, `ISqlExecutor`, `IBookingsDBAdapter`, `IBookingsController`

**Adding a new endpoint:** define route in `routes.py` → add method to `IBookingsController` and `IBookingsDBAdapter` protocols → implement in `BookingsController` and `BookingsDBAdapter` → add DTO in `dto/bookings.py` → add response schema in `schemas/bookings.py`.
