# event-admin Audit Findings

Audited: 2026-04-19

---

## CRITICAL

---

### [CRITICAL] `db/__init__.py` imports directly from `event_saver` package

**Services affected:** event-admin  
**Location:** `event-admin/event_admin/db/__init__.py:1-11`  
**Description:**  
`event_admin/db/__init__.py` imports `Base` and seven ORM model classes directly from `event_saver.db.base` and `event_saver.db.models`. This creates a hard runtime dependency on `event-saver` being installed in the same Python environment. It violates the architectural boundary between services (shared schemas should come from `event-schemas`, not peer services), breaks standalone deployability of `event-admin`, and will silently fail if `event-saver` is not on `sys.path`. The `event_admin/db/models.py` file duplicates these ORM definitions locally (correctly), making the `db/__init__.py` re-export entirely redundant.  
**Recommendation:**  
Delete the cross-service import in `db/__init__.py` and re-export only from the local `event_admin.db.models` and `event_admin.db.base`. Remove `event-saver` from any implicit path assumptions. Verify nothing else in the package imports from `event_admin.db` (the local `db/__init__.py` is unused by routes/adapters/ioc, so removal is safe).

---

### [CRITICAL] `debug=True` in `.env` disables all authentication

**Services affected:** event-admin  
**Location:** `event-admin/.env:2`, `event-admin/event_admin/middleware.py:30-31`  
**Description:**  
The committed `.env` file sets `DEBUG=True`. `JWTAuthMiddleware.dispatch()` contains an unconditional early-return when `settings.debug` is `True`, bypassing all JWT validation for every request including all `/bookings/*` routes. With this file present anyone with network access can read all booking, participant, notification, and meeting-link data with no credentials. Even if the `.env` is not deployed to production, committing it establishes a dangerous default that may be copied.  
**Recommendation:**  
Remove `DEBUG=True` from `.env` (or delete the `.env` file from version control entirely and add it to `.gitignore`). Add a `.env.example` with `DEBUG=False` as the documented default. Consider adding a startup assertion that refuses to start with `debug=True` unless `ALLOW_DEBUG=1` is also explicitly set, as a defence-in-depth measure.

---

## HIGH

---

### [HIGH] ~~`SqlExecutor` exposes write methods~~ — FIXED 2026-04-21

**Status:** FIXED. `SqlExecutor` and `ISqlExecutor` now contain only `fetch_one` and `fetch_all`. No write methods exist. DB-level read-only role enforcement remains a separate infrastructure task.

---

### [HIGH] ~~`require_admin` dependency not used~~ — FIXED (pre-existing)

**Status:** FIXED. `require_admin` is applied as `dependencies=[Depends(require_admin)]` on both `bookings_router` and `users_router`. All protected routes enforce admin role.

---

### [HIGH] ~~CORS `allow_origins=["*"]` with `allow_credentials=True`~~ — FIXED 2026-04-21

**Status:** FIXED. CORS origins now read from `Settings.cors_origins` (default `["http://localhost:5173"]`). Wildcard removed.

---

### [HIGH] ~~`list_bookings` has no pagination~~ — FIXED (pre-existing)

**Status:** FIXED. Both `list_bookings` and `list_future_email_bounced_bookings` have `limit` (1-500, default 50) and `offset` query parameters enforced server-side.

---

## MEDIUM

---

### [MEDIUM] `get_booking_details` performs 7 sequential DB round-trips per request (N+1 pattern)

**Services affected:** event-admin  
**Location:** `event-admin/event_admin/adapters/bookings_db.py:77-352`  
**Description:**  
`get_booking_details` issues one query to fetch the booking row, then six more independent `fetch_all` calls for organizer history, meeting links, email notifications, email status history, telegram notifications, chat events, and video events — all sequentially on a single session. For a busy booking this can be 7 round-trips. SQLAlchemy async does not pipeline these automatically. At low concurrency this is acceptable; under load it holds a connection for the entire duration.  
**Recommendation:**  
Combine the child-table queries into a single SQL query using `LEFT JOIN` or execute them concurrently using `asyncio.gather`. Alternatively, keep separate queries but run them in parallel with `asyncio.gather(*[executor.fetch_all(...) for ...])`. The email status history subquery already avoids the N+1 for individual notifications; apply the same pattern for other sub-lists.

---

### [MEDIUM] `BookingDetailsDto` has mutable list fields — violates frozen-dataclass contract

**Services affected:** event-admin  
**Location:** `event-admin/event_admin/dto/bookings.py:79-82, 118-136`  
**Description:**  
`BookingEmailNotificationItemDto` contains a `status_history: list[BookingEmailStatusHistoryItemDto]` field. `BookingDetailsDto` contains six `list[…]` fields. All DTOs are declared `frozen=True`, but `frozen` only prevents reassignment of the field reference — it does not make `list` contents immutable. The list objects themselves can be mutated after construction, breaking the immutability guarantee that callers rely on.  
**Recommendation:**  
Replace `list[…]` fields with `tuple[…, ...]` in all frozen DTO dataclasses, consistent with the `tuple[str, ...]` used in `BookingListFiltersDto` and `BookingFutureBouncedEmailItemDto`. Update the construction sites in `bookings_db.py` to pass tuples.

---

### [MEDIUM] Authentication middleware order is inverted — CORSMiddleware runs after JWTAuthMiddleware

**Services affected:** event-admin  
**Location:** `event-admin/event_admin/main.py:45-52`  
**Description:**  
In Starlette/FastAPI, middleware added with `add_middleware` is applied in reverse order (last-added runs first as the outermost wrapper). The current code adds `JWTAuthMiddleware` first and `CORSMiddleware` second, meaning `CORSMiddleware` is the outermost middleware and runs first — which is correct. However, this is an implicit and fragile dependency on Starlette's reverse-wrapping semantics. If the order is ever changed, JWT checks will run before CORS headers are attached to 401 responses, breaking preflight handling. The comment `# Bookings routes (auth enforced by JWTAuthMiddleware)` also implies the developer may not be aware of the ordering semantics.  
**Recommendation:**  
Add a comment explicitly documenting Starlette's reverse-add order so future maintainers understand `CORSMiddleware` must remain last in `add_middleware` calls. Alternatively, define middleware in the `lifespan` or via explicit `app.middleware` decorator ordering to make intent clear.

---

### [MEDIUM] ~~JWT default secret hardcoded~~ — FIXED (pre-existing)

**Status:** FIXED. `jwt_secret_key` uses `Field(...)` with no default. Service fails to start without explicit `JWT_SECRET_KEY`.

---

### [MEDIUM] ~~`BookingDetailsResponse` silently drops fields~~ — FIXED 2026-04-21

**Status:** FIXED. `first_seen_at`, `last_seen_at`, `updated_at` added to `BookingDetailsResponse` and `from_dto()`. Other omissions (`BookingOrganizerHistoryItemResponse`, `BookingMeetingLinkItemResponse`) are intentional — internal audit fields not exposed in API (comments added in `schemas/bookings.py`).

---

### [MEDIUM] `admin_users` table has ORM model and migration SQL inline in docstring — no actual migration

**Services affected:** event-admin, event-saver  
**Location:** `event-admin/event_admin/db/models.py:11-26`  
**Description:**  
The `AdminUser` ORM model includes migration SQL in a docstring comment rather than in a proper Alembic migration. The `admin_users` table is service-specific to `event-admin` (not written by `event-saver`) yet there is no migration file anywhere in the monorepo for it. Schema changes to `admin_users` will require manual SQL execution with no audit trail.  
**Recommendation:**  
Determine the correct home for `admin_users` migrations. Since this table is `event-admin`-specific, add an `alembic/` directory to `event-admin` for this table only, or manage it via a separate migration script tracked in `scripts/`. Remove the inline SQL comment from the model docstring once a proper migration exists.

---

### [MEDIUM] ~~Login endpoint does not log failed auth attempts~~ — FIXED 2026-04-21

**Status:** FIXED. Each failure path logs `login_failed` with reason (`user_not_found`, `user_inactive`, `bad_password`, `bad_totp`). Success logs `login_success`. Request correlation via `X-Request-ID` contextvars.

---

### [MEDIUM] ~~No request ID / correlation ID~~ — FIXED 2026-04-21

**Status:** FIXED. `JWTAuthMiddleware` generates `request_id` (UUID4) per request, binds to structlog contextvars, returns as `X-Request-ID` response header. Cleanup via `try/finally`.

---

## LOW

---

### [LOW] ~~`booking_uids` filter accepts arbitrary strings~~ — FIXED 2026-04-21

**Status:** FIXED. `booking_uids` limited to max 200 items with HTTP 400 guard.

---

### [LOW] No test coverage

**Services affected:** event-admin  
**Location:** `event-admin/` (no `tests/` directory found)  
**Description:**  
No unit or integration tests exist for any layer — routes, controllers, adapters, auth, or middleware. Critical paths such as the login flow, token validation, the debug bypass, and the booking detail query have zero automated coverage.  
**Recommendation:**  
Add at minimum: (1) unit tests for `PasswordService` and `TOTPService`, (2) integration tests for the login endpoint using `httpx.AsyncClient` + a test database, (3) tests for `JWTAuthMiddleware` verifying the debug bypass is not active when `debug=False`.

---

### [LOW] ~~`logger.py` suppresses unused loggers~~ — FIXED 2026-04-21

**Status:** FIXED. Removed `aiokafka`, `asyncio_redis`, `urllib3`, `botocore` suppressions. Only `httpcore` (httpx dependency) retained.

---

### [LOW] `GET /auth/logout` is a no-op with no actual session invalidation

**Services affected:** event-admin  
**Location:** `event-admin/event_admin/routes.py:56-58`  
**Description:**  
`POST /auth/logout` returns 204 but does nothing — JWTs are stateless and the endpoint issues no token revocation. If a token is stolen between issuance and its 24-hour expiry there is no mechanism to invalidate it. The frontend may rely on this endpoint providing security it does not actually deliver.  
**Recommendation:**  
Either: (a) implement a server-side token blocklist (e.g. Redis set of revoked `jti` claims with TTL matching `jwt_expire_minutes`), or (b) shorten the JWT TTL significantly (e.g. 15 minutes) and implement refresh tokens. At minimum, add a comment to the endpoint explaining that logout is client-side only (token deletion from storage) so the frontend team is not misled.

---

### [LOW] `jwt_expire_minutes` defaults to 24 hours — excessively long for an admin token

**Services affected:** event-admin  
**Location:** `event-admin/event_admin/config.py:31`  
**Description:**  
Admin JWTs are valid for 24 hours by default. Given there is no token revocation mechanism (see above), a stolen admin token grants full access to all booking data for up to 24 hours.  
**Recommendation:**  
Reduce `jwt_expire_minutes` default to 60 minutes or less. Implement token refresh if the frontend needs longer sessions.

---

### [LOW] `BookingEmailStatusHistoryItemDto.source_event_id` is non-optional but can be NULL in DB schema

**Services affected:** event-admin  
**Location:** `event-admin/event_admin/dto/bookings.py:62`, `event-admin/event_admin/db/models.py:254`  
**Description:**  
`BookingEmailStatusHistoryItemDto.source_event_id` is typed `str` (non-optional). The ORM model `BookingEmailStatusHistory.source_event_id` is `nullable=False`, consistent. However `booking_email_status_history.source_event_id` has a FK to `events.event_id` with `ondelete="CASCADE"` — if the referenced event is deleted the FK row is deleted too, not the field nulled. This is consistent. But if the schema is ever changed to allow NULL (e.g. during event-saver migration work), the DTO will fail at runtime with a `ValidationError` rather than a graceful error. Minor type-safety concern.  
**Recommendation:**  
No immediate action required, but add a note in `BookingEmailStatusHistoryItemDto` that `source_event_id` is expected non-null per current schema. Revisit if the FK constraint changes.

---

### [LOW] `db/models.py` — `BookingRecord` model missing index on `booking_uid` despite being a lookup key

**Services affected:** event-admin (read queries), event-saver (authoritative schema)  
**Location:** `event-admin/event_admin/db/models.py:53`, `event-admin/event_admin/adapters/bookings_db.py:78-96`  
**Description:**  
`GET /bookings/{booking_uid}` queries `WHERE b.booking_uid = :booking_uid`. The `BookingRecord` ORM model defines a `UniqueConstraint` on `booking_uid` (which implicitly creates a B-tree index in PostgreSQL), so this query is in fact indexed. However the model does not define an explicit `Index("ix_bookings_booking_uid", "booking_uid")` — the index is a side-effect of the constraint. If the schema is ever inspected programmatically via SQLAlchemy's `inspect()` (e.g. in tests or documentation tooling) the index will not appear in `__table_args__` explicitly.  
**Recommendation:**  
This is a very low-priority style issue. The index exists. If desired, add an explicit `Index` alongside the `UniqueConstraint` for clarity, but this can be deferred.

---

## Summary

| Severity | Total | Fixed | Remaining |
|----------|-------|-------|-----------|
| CRITICAL | 2 | 0 | 2 |
| HIGH     | 4 | 4 | 0 |
| MEDIUM   | 7 | 4 | 3 |
| LOW      | 7 | 2 | 5 |
| **Total**| **20** | **10** | **10** |

### Top 3 Concerns

1. **`db/__init__.py` imports from `event_saver`** (CRITICAL) — Direct cross-service package import breaks the monorepo's service isolation, makes `event-admin` non-deployable as a standalone container, and is the only finding that could cause an immediate import-time crash in any environment where `event-saver` is not co-installed.

2. **`DEBUG=True` in committed `.env` disables all authentication** (CRITICAL) — All booking, notification, meeting-link, and participant data is accessible without any credentials when the service starts with this file. The `.env` is committed to version control, creating a discoverability risk.

3. **`SqlExecutor` exposes write methods with no read-only DB role** (HIGH) — The service is read-only only by convention. Both the `execute()` (with `session.commit()`) and `execute_in_transaction()` methods are live in the codebase and advertised via the `ISqlExecutor` interface. Without a read-only Postgres role the "read-only API" guarantee is one accidental adapter method away from being violated.

### Architecture Quality Summary

The overall architecture is sound: Protocol-based interfaces, frozen DTOs, `from_dto()` response schemas, DishkaRoute DI, and structlog are all correctly applied. The layer boundaries (routes → controllers → adapters → sql.py) are followed consistently. There is no `alembic/` directory (correct). Controllers are thin (pure delegation). The main structural gaps are the cross-service import in `db/__init__.py`, the absence of pagination, the write-capable `SqlExecutor`, and the lack of any test coverage.
