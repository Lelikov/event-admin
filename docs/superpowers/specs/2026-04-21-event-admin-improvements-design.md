# Event-Admin Service Improvements — Design Spec

**Date:** 2026-04-21
**Scope:** Comprehensive improvements across security, data integrity, observability, and code quality
**Approach:** Domain-grouped phases, severity-ordered within each phase

---

## Phase 1: Security & Auth

### 1.1 Fix syntax error in middleware.py

**Problem:** `except jwt.InvalidTokenError, KeyError:` is Python 2 syntax — crashes at runtime on invalid tokens.
**Fix:** Replace with `except (jwt.InvalidTokenError, KeyError):`.

### 1.2 Settings via DI in middleware

**Problem:** `JWTAuthMiddleware` instantiates `Settings()` on every request instead of receiving it via constructor.
**Fix:** Accept `settings` in `__init__`, pass it when registering middleware in `main.py`.

### 1.3 Remove hardcoded JWT secret default

**Problem:** `jwt_secret_key` defaults to `"dev-jwt-secret-change-in-prod"` — if env var is missing, tokens are trivially forgeable.
**Fix:** Remove default value. Service fails to start without explicit `JWT_SECRET_KEY`.

### 1.4 Consolidate JWT validation

**Problem:** Token is decoded twice per request — once in `JWTAuthMiddleware`, once in `get_current_user()` dependency.
**Fix:** Middleware stores decoded payload in `request.state.user`. `get_current_user()` reads from `request.state` instead of re-decoding.

### 1.5 Fix CORS configuration

**Problem:** `allow_origins=["*"]` with `allow_credentials=True` violates W3C CORS spec; browsers reject credentialed requests to wildcard origins.
**Fix:** Add `cors_origins: list[str]` to `Settings` (default `["http://localhost:5173"]`). Use in CORS middleware config.

### 1.6 Auth audit logging

**Problem:** No logging for login attempts — no visibility into brute-force or credential stuffing.
**Fix:** Add structlog calls in login endpoint: `login_success(email, role)` and `login_failed(email, reason)` for each failure path (bad password, inactive user, bad TOTP).

---

## Phase 2: Read-only Enforcement

### 2.1 Remove write methods from SqlExecutor

**Problem:** `ISqlExecutor` and `SqlExecutor` expose `execute()` (with auto-commit) and `execute_in_transaction()` — the service is read-only and should not have write capabilities.
**Fix:** Remove `execute()` and `execute_in_transaction()` from both the interface and implementation. Only `fetch_one()` and `fetch_all()` remain.

---

## Phase 3: Data Integrity

### 3.1 Tuple instead of list in frozen DTOs

**Problem:** Frozen dataclasses contain `list[...]` fields. `frozen=True` prevents reassignment but not mutation of list contents.
**Fix:** Replace all `list[...]` with `tuple[..., ...]` in `dto/bookings.py`. Update construction sites in `bookings_db.py` to pass tuples.

### 3.2 Enum for current_statuses

**Problem:** `current_statuses` filter accepts arbitrary strings — no validation against known booking statuses.
**Fix:** Add `BookingStatus(StrEnum)` with known values. Use in `BookingListFiltersDto` and route query parameter.

### 3.3 Audit from_dto() — add missing fields

**Problem:** `BookingDetailsResponse.from_dto()` silently drops `first_seen_at`, `last_seen_at`, `updated_at` from the DTO. Similar gaps in `BookingOrganizerHistoryItemResponse` and `BookingMeetingLinkItemResponse`.
**Fix:** Add missing timestamp fields to response schemas. Verify all `from_dto()` methods map every DTO field or have explicit comments for intentional exclusions.

---

## Phase 4: Observability

### 4.1 Request correlation ID

**Problem:** No request-scoped identifier in logs — debugging multi-step failures is difficult.
**Fix:** Generate `uuid4` per request in middleware. Bind via `structlog.contextvars.bind_contextvars(request_id=...)`. Return `X-Request-ID` in response headers.

### 4.2 Remove dead logger suppressions

**Problem:** `logger.py` silences `aiokafka` and `asyncio_redis` — neither is a dependency of this service.
**Fix:** Remove the two suppression lines.

---

## Phase 5: Cleanup

### 5.1 Validate booking_uids length

**Problem:** `booking_uids` query param accepts arbitrary number of items — potential query DoS.
**Fix:** Limit to max 200 items via FastAPI `Query()`. Limit individual UID length to 100 chars.

### 5.2 Add OpenAPI descriptions

**Problem:** FastAPI auto-generates Swagger docs but endpoints have no summaries or descriptions.
**Fix:** Add `summary` and `description` to each route decorator.

---

## Out of Scope

- Test coverage (separate initiative)
- Token revocation / refresh tokens (separate auth redesign)
- Admin user CRUD endpoints (separate feature)
- Database-level read-only role creation (infrastructure change)
- Pagination for `list_future_email_bounced_bookings` (already has limit/offset in adapter)
