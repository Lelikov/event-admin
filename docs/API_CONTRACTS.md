# event-admin API Contracts

All endpoints are served by a single FastAPI application (`main.py:41`).

Base URL: configured at deployment (default `http://localhost:8000`).

---

## Authentication

JWT Bearer tokens issued by `POST /auth/login`. All non-public endpoints require a valid `Authorization: Bearer <token>` header. The `JWTAuthMiddleware` (`middleware.py`) rejects requests without a valid token (returns 401). **Authentication is enforced in every environment** — there is no DEBUG bypass (removed in audit-v2).

When `JWT_AUDIENCE` / `JWT_ISSUER` are configured, minted tokens carry matching `aud`/`iss` claims and the middleware enforces them; when unset, tokens carrying those claims still verify (rollout tolerance, mirrored in `event-users`).

All responses include an `X-Request-ID` header (UUID) for log correlation. Clients may send their own `X-Request-ID` header; if present, it is echoed back.

---

## Public Endpoints

### GET /health

| | |
|---|---|
| **Auth** | None |
| **Query params** | None |
| **Response** | `200 OK` -- `{"status": "ok"}` |
| **Reference** | `routes.py:31-34` |

---

### POST /auth/login

| | |
|---|---|
| **Auth** | None (public) |
| **Request body** | `LoginRequest` (JSON) |
| **Response** | `200 OK` -- `LoginResponse` |
| **Error codes** | `401 Unauthorized` -- invalid credentials, inactive user, bad/replayed TOTP; `429 Too Many Requests` -- lockout after `LOGIN_MAX_FAILURES` failures per client-IP+email within `LOGIN_LOCKOUT_SECONDS` |
| **Notes** | TOTP codes are single-use: a code accepted once is rejected for the rest of its validity window. Failure counter resets on successful login. |
| **Reference** | `routes.py`, `schemas/auth.py`, `services/login_guard.py` |

**Request body schema (`LoginRequest`):**

| Field | Type | Required |
|---|---|---|
| `email` | EmailStr | Yes |
| `password` | str | Yes |
| `totp_code` | str | Yes |

**Response schema (`LoginResponse`):**

| Field | Type |
|---|---|
| `access_token` | str |
| `token_type` | str (always `"Bearer"`) |
| `role` | str (`"admin"` or `"user"`) |

---

### POST /auth/logout

| | |
|---|---|
| **Auth** | Bearer token (middleware-enforced) |
| **Request body** | None |
| **Response** | `204 No Content` |
| **Notes** | No-op; JWT is stateless, no server-side revocation. Client should discard the token. |
| **Reference** | `routes.py:56-58` |

---

## Protected Endpoints (require `admin` role)

All `/bookings` routes are protected by both:
1. `JWTAuthMiddleware` (token signature validation) -- `middleware.py`
2. `Depends(require_admin)` on `bookings_router` (role = `admin` required) -- `routes.py:28`, `auth.py:60-63`

A valid token with `role=user` will receive `403 Forbidden`.

---

### GET /bookings

| | |
|---|---|
| **Auth** | Bearer token + admin role |
| **Response** | `200 OK` -- `list[BookingListItemResponse]` |
| **Error codes** | `401` (missing/invalid/expired token), `403` (non-admin role) |
| **Reference** | `routes.py:61-78`, `schemas/bookings.py:30-63` |

**Query parameters:**

| Param | Type | Default | Constraints | Description |
|---|---|---|---|---|
| `booking_uids` | list[str] (repeated) | None | max 200 items | Filter by booking UIDs (ANY match) |
| `current_statuses` | list[BookingStatus] (repeated) | None | enum: `created`, `confirmed`, `cancelled`, `rescheduled`, `completed`, `no_show` | Filter by current status values |
| `current_organizer_user_ids` | list[UUID] (repeated) | None | -- | Filter by organizer user IDs |
| `current_client_user_ids` | list[UUID] (repeated) | None | -- | Filter by client user IDs |
| `limit` | int | 50 | ge=1, le=500 | Page size |
| `offset` | int | 0 | ge=0 | Pagination offset |

**Response item schema (`BookingListItemResponse`):**

| Field | Type |
|---|---|
| `id` | int |
| `booking_uid` | str |
| `first_seen_at` | datetime |
| `last_seen_at` | datetime |
| `start_time` | datetime | None |
| `end_time` | datetime | None |
| `current_status` | str | None |
| `created_at` | datetime |
| `updated_at` | datetime |
| `organizer_participant` | ParticipantResponse | None |
| `client_participant` | ParticipantResponse | None |

---

### GET /bookings/future-email-bounced

| | |
|---|---|
| **Auth** | Bearer token + admin role |
| **Response** | `200 OK` -- `list[BookingFutureBouncedEmailItemResponse]` |
| **Error codes** | `401`, `403` |
| **Reference** | `routes.py:81-91`, `schemas/bookings.py:242-269` |

**Query parameters:**

| Param | Type | Default | Constraints |
|---|---|---|---|
| `limit` | int | 50 | ge=1, le=500 |
| `offset` | int | 0 | ge=0 |

**Response item schema (`BookingFutureBouncedEmailItemResponse`):**

| Field | Type |
|---|---|
| `id` | int |
| `booking_uid` | str |
| `start_date` | datetime |
| `end_time` | datetime | None |
| `current_status` | str | None |
| `organizer_participant` | ParticipantResponse | None |
| `client_participant` | ParticipantResponse | None |
| `email_bounce_statuses` | list[str] |

---

### GET /bookings/{booking_uid}

| | |
|---|---|
| **Auth** | Bearer token + admin role |
| **Path params** | `booking_uid` (str, min_length=1) |
| **Response** | `200 OK` -- `BookingDetailsResponse` |
| **Error codes** | `401`, `403`, `404 Not Found` (booking does not exist) |
| **Reference** | `routes.py:94-105`, `schemas/bookings.py:196-239` |

**Response schema (`BookingDetailsResponse`):**

| Field | Type |
|---|---|
| `id` | int |
| `booking_uid` | str |
| `first_seen_at` | datetime |
| `last_seen_at` | datetime |
| `start_time` | datetime | None |
| `end_time` | datetime | None |
| `current_status` | str | None |
| `created_at` | datetime |
| `updated_at` | datetime |
| `current_organizer_participant` | ParticipantResponse | None |
| `current_client_participant` | ParticipantResponse | None |
| `organizer_history` | list[BookingOrganizerHistoryItemResponse] |
| `meeting_links` | list[BookingMeetingLinkItemResponse] |
| `email_notifications` | list[BookingEmailNotificationItemResponse] |
| `telegram_notifications` | list[BookingTelegramNotificationItemResponse] |
| `chat_events` | list[BookingChatEventItemResponse] |
| `video_events` | list[BookingVideoEventItemResponse] |

**Nested response schemas:**

- `ParticipantResponse`: `{ user_id: UUID | None }`
- `BookingOrganizerHistoryItemResponse`: `{ id, organizer_participant, effective_from }`
- `BookingMeetingLinkItemResponse`: `{ id, participant, meeting_url, created_at }`
- `BookingEmailNotificationItemResponse`: `{ id, participant, trigger_event, sent_at, last_status, status_history[] }`
- `BookingEmailStatusHistoryItemResponse`: `{ id, status, clicked_url, created_at }`
- `BookingTelegramNotificationItemResponse`: `{ id, participant, trigger_event, source_event_id, sent_at, created_at }`
- `BookingChatEventItemResponse`: `{ id, chat_event_type, participant, is_read, text_preview, occurred_at, updated_at }`
- `BookingVideoEventItemResponse`: `{ id, raw_event_id, video_event_type, participant_role, participant, event_time, payload }`

---

### POST /bookings/{booking_uid}/reassign-client

Change the client assigned to a booking to an existing client user. Publishes CloudEvent `booking.client_reassigned` (source `admin`) via event-receiver; event-receiver routes it to `events.booking.lifecycle`, consumed by event-saver.

| | |
|---|---|
| **Auth** | Bearer token + admin role |
| **Path params** | `booking_uid` (str) |
| **Request body** | `{"new_client_email": "client@example.com"}` |
| **Response** | `202 Accepted` -- `{"status": "accepted"}` (processing is asynchronous) |
| **Error codes** | `401`, `403`, `404` (booking not found / no client user with this email), `422` (invalid email), `502` (publish to event-receiver failed — action NOT applied) |
| **Notes** | Booking existence is verified against the DB **before** publishing; the new client email is matched lowercased against role=`client` in event-users. |

**Published payload** (`BookingClientReassignedPayload`):

```json
{
  "booking_uid": "book-123",
  "new_client_user_id": "<uuid>",
  "requested_by": "<admin email from JWT sub>"
}
```

---

## Users Proxy Endpoints (require `admin` role)

All `/api/users` routes are protected by both `JWTAuthMiddleware` and `Depends(require_admin)`. They proxy requests to the `event-users` service and **re-serialize responses through typed allowlist models** (`schemas/users_proxy.py`: `ProxiedUser`, `ProxiedUsersListResponse`, ...) — unknown upstream fields are dropped, never forwarded. Upstream HTTP errors are forwarded as status codes. Responses are cached in-process (`UsersCache`, default TTL 300s).

**`ProxiedUser` fields:** `id`, `email`, `name`, `role`, `time_zone`, `contacts[{id, user_id, channel, contact_id, created_at, updated_at}]`, `created_at`, `updated_at`.

---

### GET /api/users

| | |
|---|---|
| **Auth** | Bearer token + admin role |
| **Response** | `200 OK` -- `ProxiedUsersListResponse` (`{"items": [ProxiedUser], "total", "limit", "offset"}`) |
| **Error codes** | `401`, `403`, upstream error statuses forwarded |

**Query parameters:**

| Param | Type | Default | Description |
|---|---|---|---|
| `email` | str | None | Filter by email (forwarded to event-users) |
| `role` | str | None | Filter by role (forwarded to event-users) |
| `limit` | int | 50 | Page size (ge=1, le=500) |
| `offset` | int | 0 | Pagination offset (ge=0) |

---

### POST /api/users/by-ids

| | |
|---|---|
| **Auth** | Bearer token + admin role |
| **Request body** | `UsersByIdsRequest`: `{"ids": ["<uuid>", ...]}` (typed; max 200 items) |
| **Response** | `200 OK` -- `ProxiedUsersByIdsResponse` (`{"items": [ProxiedUser]}`) |
| **Error codes** | `401`, `403`, `422` (non-list body, invalid UUID, or >200 IDs), upstream error statuses forwarded |

---

### GET /api/users/id/{user_id}

| | |
|---|---|
| **Auth** | Bearer token + admin role |
| **Path params** | `user_id` (UUID) |
| **Response** | `200 OK` -- `ProxiedUser` |
| **Error codes** | `401`, `403`, `404` (forwarded from event-users) |

---

### POST /api/users/id/{user_id}/change-email

Запросить смену email клиента. Публикует CloudEvent `user.email.change_requested` через event-receiver; возвращает 202 Accepted немедленно (обработка асинхронная).

| | |
|---|---|
| **Auth** | Bearer token + admin role |
| **Path params** | `user_id` (UUID) |
| **Request body** | `{"new_email": "new@example.com"}` |
| **Response** | `202 Accepted` -- `{"status": "accepted"}` |
| **Error codes** | `401`, `403`, `400` (не client / email совпадает с текущим), `404` (пользователь не найден), `409` (email уже занят другим клиентом), `422` (невалидный email), `502` (публикация в event-receiver не удалась — изменение НЕ применено) |

**Flow**: event-admin → `POST /event/admin` (event-receiver, static API key) → `events.user.email` (RabbitMQ) → event-users.

**Normalization**: `new_email` приводится к нижнему регистру один раз; то же значение используется и для проверки уникальности, и в публикуемом payload (исключает case-variant дубликаты ниже по потоку). Проверка уникальности — TOCTOU by design; event-users перепроверяет при консьюме.

---

### GET /api/users/id/{user_id}/email-changelog

Получить историю изменений email клиента. Проксирует запрос к `GET /api/users/{user_id}/email-changelog` в event-users.

| | |
|---|---|
| **Auth** | Bearer token + admin role |
| **Path params** | `user_id` (UUID) |
| **Response** | `200 OK` -- `ProxiedEmailChangelogResponse` (`{"items": [...], "total": int}`) |
| **Error codes** | `401`, `403`, `404` (forwarded from event-users) |

**Query parameters:**

| Param | Type | Default | Description |
|---|---|---|---|
| `limit` | int | 50 | Размер страницы (ge=1, le=500) |
| `offset` | int | 0 | Смещение для пагинации (ge=0) |

**Response item schema**:

| Field | Type |
|---|---|
| `id` | UUID |
| `old_email` | str |
| `new_email` | str |
| `changed_by` | str |
| `changed_at` | datetime |

---

## Cache Endpoints

### POST /api/users/cache/invalidate

| | |
|---|---|
| **Auth** | `Authorization: Bearer <CACHE_INVALIDATION_TOKEN>` (separate token, **not** a user JWT) |
| **Request body** | None |
| **Response** | `204 No Content` |
| **Error codes** | `401 Unauthorized` -- missing or wrong invalidation token |
| **Notes** | Called by `event-users` to flush the in-memory `UsersCache` after create/update operations. Uses a dedicated shared secret (`CACHE_INVALIDATION_TOKEN`), not an admin JWT; compared constant-time via `hmac.compare_digest`. |

---

## Common Error Responses

| Status | Body | Cause |
|---|---|---|
| 401 | `{"detail": "Missing bearer token"}` | No `Authorization` header or malformed |
| 401 | `{"detail": "Token expired"}` | JWT `exp` claim in the past |
| 401 | `{"detail": "Invalid token"}` | Signature mismatch, malformed JWT |
| 401 | `{"detail": "Invalid credentials"}` | Login: wrong email/password/TOTP or inactive user |
| 403 | `{"detail": "Admin access required"}` | Valid token but `role != "admin"` |
| 404 | `{"detail": "Booking with uid='...' not found"}` | No booking row matches path param |
| 429 | `{"detail": "Too many failed login attempts; try again later"}` | Login lockout (per client-IP+email) |
| 502 | `{"detail": "Failed to publish event to event-receiver; the action was NOT applied", "event_type": "...", "upstream_status": ...}` | event-receiver down/slow/rejecting during change-email or reassign-client |

---

## Notes

- Pagination params (`limit`, `offset`) are enforced server-side with `limit` capped at 500 (`routes.py:67-68, 87-88`).
- Filter list params use repeated query string keys (e.g. `?booking_uids=abc&booking_uids=def`).
- `BookingDetailsResponse` now includes `first_seen_at`, `last_seen_at`, `updated_at` from the DTO.
- `current_statuses` filter accepts `BookingStatus` enum values (`enums.py`).
- `booking_uids` filter is limited to 200 items maximum.
