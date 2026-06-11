# event-admin Audit Findings

Audited: **audit-v2, 2026-06-11** (previous audit: 2026-04-19).
All audit-v2 findings were fixed on branch `audit-fixes` unless listed under "Accepted / Deferred".
Every fix is covered by tests (`uv run pytest`, 75+ tests; `uv run ruff check .` clean).

---

## Fixed in audit-v2 (2026-06-11)

### CRITICAL

1. **DEBUG=True disabled all authentication** — `JWTAuthMiddleware` returned a synthetic admin payload (`{"sub": "debug@local", "role": "admin"}`) for every request when `settings.debug` was true; local `.env` shipped `DEBUG=True` + placeholder `JWT_SECRET_KEY`.
   **Fix:** the bypass was **removed entirely** (chosen over a guard flag as the safest option — auth is now enforced identically in every environment; there is no code path that skips JWT validation). `DEBUG` now only switches log rendering and relaxes the new startup secret-strength validation. Outside DEBUG the service refuses to start with secrets `<16` chars or known placeholders (`JWT_SECRET_KEY`, `USERS_SERVICE_API_TOKEN`, `CACHE_INVALIDATION_TOKEN`, `EVENT_RECEIVER_API_KEY`). `.env.example` added. Regression test: `tests/test_middleware.py::test_debug_true_does_not_bypass_auth`.
   *Note:* the local gitignored `.env` keeps `DEBUG=True` only because its secrets must match the weak dev values of neighbor services (event-users `JWT_SECRET_KEY`, event-receiver `ADMIN_API_KEY`); this is now harmless for auth.

### HIGH

2. **`get_booking_details` ran 7 concurrent queries on one `AsyncSession` via `asyncio.gather`** — SQLAlchemy's `AsyncSession` forbids concurrent operations, so `GET /bookings/{uid}` 500-ed (`InvalidRequestError` / asyncpg `InterfaceError`) on essentially every call.
   **Fix:** queries run sequentially with an explanatory comment. Regression test uses a concurrency-detecting fake executor that fails if `gather` is reintroduced (`tests/test_bookings_db.py`).

### MEDIUM

3. **EventPublisher had no error handling** — receiver downtime/4xx/5xx surfaced as unhandled 500s with no failure logging or retry.
   **Fix:** tenacity retries for transport errors (`EVENT_PUBLISH_ATTEMPTS`, default 3, exponential backoff); all final failures raise `EventPublishError` (structured: event_type, source, upstream_status), logged, and mapped to **502** with `"the action was NOT applied"`. Timeout configurable (`EVENT_PUBLISH_TIMEOUT_SECONDS`).
4. **reassign-client published for arbitrary `booking_uid`** — a typo'd uid returned 202 and emitted a CloudEvent that could create phantom lifecycle rows in event-saver.
   **Fix:** booking existence verified via `IBookingsController` before publishing; 404 otherwise.
5. **No brute-force protection on /auth/login; TOTP replayable; malformed secret 500-ed.**
   **Fix:** `LoginGuard` (APP-scoped, in-memory): lockout per client-IP+email (`LOGIN_MAX_FAILURES`/`LOGIN_LOCKOUT_SECONDS` → 429), TOTP single-use within its 90s validity span, counter reset on success. `TOTPService.verify` fails closed on malformed/empty secrets.
6. **`admin_users` DDL lived only in a model docstring.**
   **Fix:** tracked idempotent DDL in `scripts/admin_users.sql` with ownership note (event-saver owns everything else; event-admin must not own Alembic). Sync test in `tests/test_admin_users_ddl.py`.
7. **Zero test coverage.**
   **Fix:** pytest + pytest-asyncio bootstrapped; 75+ tests over an ASGI harness with a fake DI provider: middleware matrix, login/lockout/replay, booking details (incl. concurrency regression), publisher retry/502 paths, users-proxy typing, cache invalidation, CORS posture, JWT claims, config validation, DDL sync.
8. **Doc drift** — "read-only service", missing `EVENT_RECEIVER_*` env vars, undocumented reassign endpoint, wrong receiver-downtime claim.
   **Fix:** SERVICE_OVERVIEW / API_CONTRACTS / DATA_MODEL / DEPENDENCIES / CLAUDE.md rewritten to match reality (this commit).

### LOW

9. **24h JWT lifetime** → default `JWT_EXPIRE_MINUTES=60`; optional `JWT_AUDIENCE`/`JWT_ISSUER` claim binding added (tolerant rollout, mirrors event-users).
10. **Implicit middleware ordering** → explicit comment at the `add_middleware` block (CORS last = outermost) + test that 401s carry CORS headers.
11. **Cache invalidation token compared with `!=`** → `hmac.compare_digest`; strong token enforced by startup validation.
12. **tenacity declared but unused** → now used for publish retries (see #3).
13. **Untyped users-proxy passthrough** → typed allowlist response models (`schemas/users_proxy.py`); unknown upstream fields are dropped (tested).
14. **`by-ids` untyped dict body (non-list `ids` → 500)** → `UsersByIdsRequest` (list[UUID], max 200) → 422 on malformed bodies.
15. **Settings built via three independent paths** → single `get_settings()` + `create_app()` factory; DI, middleware, CORS, and token minting share one instance.
16. **`change_user_email` published mixed-case `new_email` while validating lowercased** → normalized once, validated and published lowercased.
17. **CORS `allow_credentials=True` + wildcard methods/headers** (security cross-cut) → credentials dropped (auth is a Bearer header, not cookies); methods/headers restricted to GET/POST/OPTIONS and Authorization/Content-Type/X-Request-ID.
18. **Deprecated path-segment lookup** → `UsersClient.get_user_by_email_role` migrated to `GET /api/users/by-identity?email=&role=` (per event-users deprecation).
19. **Prose-only error `detail` strings (frontend matched exact English text)** → RESOLVED (audit-v2 follow-up #6, 2026-06-11): every error path returns `detail = {"code": "<stable_snake_case>", "message": "<human text>"}` via `errors.http_error()` (routes, auth deps, JWT middleware, 502 publish handler). HTTP status codes unchanged. Catalog in `docs/API_CONTRACTS.md` § Common Error Responses; event-admin-frontend now translates by `code`.

---

## Accepted / Deferred

- **Raw API key as `Authorization` value to event-receiver (no Bearer scheme)** — RESOLVED (audit-v2 follow-up #7, 2026-06-11): coordinated two-side change shipped. `EventPublisherClient` sends `Authorization: Bearer <key>`; event-receiver's `ingest_admin` accepts only the Bearer scheme (token compared constant-time, malformed headers rejected). event-notifier's `DeliveryResultPublisher` (the other /event/admin sender) switched in the same change set.
- **`event-receiver/QUEUES_DIGEST.md` missing `booking.client_reassigned` row** — lives in the event-receiver repo (out of scope for this fixer); the routing is documented in root `docs/architecture/MESSAGE_CONTRACTS.md` and in `docs/DEPENDENCIES.md` here.
- **In-memory LoginGuard/UsersCache** — per-process; acceptable for the current single-instance deployment. Multi-replica deployments need a shared store (Redis-class) for global lockout/replay tracking — documented limitation.
- **No server-side JWT revocation / refresh tokens** — lifetime reduced to 60 min; logout remains an honest client-side no-op. Refresh tokens deferred until the frontend needs longer sessions.
- **TOCTOU on change-email uniqueness pre-check** — by design; event-users re-validates on consume.

---

## Resolved in previous audit (2026-04-21)

- Login failures not logged → per-reason `login_failed` / `login_success` events
- No request-id correlation → `X-Request-ID` + structlog contextvars
- Mutable list fields in frozen DTOs → tuples
- Settings re-instantiated per request in middleware → constructor injection
- Double JWT decode → middleware stores payload in `request.state`
- CORS `allow_origins=["*"]` → configurable `cors_origins`
- `BookingDetailsResponse` missing timestamp fields → added
- Dead logger suppressions → removed
