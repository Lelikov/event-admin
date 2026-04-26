# event-admin API Contracts

All endpoints are served by a single FastAPI application (`main.py:41`).

Base URL: configured at deployment (default `http://localhost:8000`).

---

## Authentication

JWT Bearer tokens issued by `POST /auth/login`. All non-public endpoints require a valid `Authorization: Bearer <token>` header. The `JWTAuthMiddleware` (`middleware.py:17-75`) rejects requests without a valid token (returns 401).

When `DEBUG=True`, middleware bypasses JWT validation entirely (development only).

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
| **Error codes** | `401 Unauthorized` -- invalid credentials, inactive user, bad TOTP |
| **Reference** | `routes.py:37-53`, `schemas/auth.py:4-13` |

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

## Users Proxy Endpoints (require `admin` role)

All `/api/users` routes are protected by both `JWTAuthMiddleware` and `Depends(require_admin)`. They proxy requests to the `event-users` service and return its responses verbatim. Upstream HTTP errors are forwarded as-is. Responses are cached in-process (`UsersCache`, default TTL 300s).

---

### GET /api/users

| | |
|---|---|
| **Auth** | Bearer token + admin role |
| **Response** | `200 OK` -- passthrough from `event-users` (`{"items": [...], "total": int}`) |
| **Error codes** | `401`, `403`, upstream errors forwarded |
| **Reference** | `routes.py:147-162` |

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
| **Request body** | `{"ids": ["<uuid>", ...]}` (max 200 items) |
| **Response** | `200 OK` -- `{"items": [...]}` passthrough from `event-users` |
| **Error codes** | `401`, `403`, `422` (invalid UUID or >200 IDs), upstream errors forwarded |
| **Reference** | `routes.py:165-187` |

---

### GET /api/users/id/{user_id}

| | |
|---|---|
| **Auth** | Bearer token + admin role |
| **Path params** | `user_id` (UUID) |
| **Response** | `200 OK` -- single user object passthrough from `event-users` |
| **Error codes** | `401`, `403`, `404` (forwarded from event-users) |
| **Reference** | `routes.py:190-202` |

---

### POST /api/users/id/{user_id}/change-email

Запросить смену email клиента. Публикует CloudEvent `user.email.change_requested` через event-receiver; возвращает 202 Accepted немедленно (обработка асинхронная).

| | |
|---|---|
| **Auth** | Bearer token + admin role |
| **Path params** | `user_id` (UUID) |
| **Request body** | `{"new_email": "new@example.com"}` |
| **Response** | `202 Accepted` -- `{}` |
| **Error codes** | `401`, `403`, `404` (пользователь не найден), `422` (невалидный email) |

**Flow**: event-admin → `POST /event/admin` (event-receiver, static API key) → `events.user.email` (RabbitMQ) → event-users.

---

### GET /api/users/id/{user_id}/email-changelog

Получить историю изменений email клиента. Проксирует запрос к `GET /api/users/{user_id}/email-changelog` в event-users.

| | |
|---|---|
| **Auth** | Bearer token + admin role |
| **Path params** | `user_id` (UUID) |
| **Response** | `200 OK` -- `{"items": [...], "total": int}` passthrough от event-users |
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
| **Notes** | Called by `event-users` to flush the in-memory `UsersCache` after create/update operations. Uses a dedicated shared secret (`CACHE_INVALIDATION_TOKEN`), not an admin JWT. |
| **Reference** | `routes.py:208-223` |

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

---

## Notes

- Pagination params (`limit`, `offset`) are enforced server-side with `limit` capped at 500 (`routes.py:67-68, 87-88`).
- Filter list params use repeated query string keys (e.g. `?booking_uids=abc&booking_uids=def`).
- `BookingDetailsResponse` now includes `first_seen_at`, `last_seen_at`, `updated_at` from the DTO.
- `current_statuses` filter accepts `BookingStatus` enum values (`enums.py`).
- `booking_uids` filter is limited to 200 items maximum.
