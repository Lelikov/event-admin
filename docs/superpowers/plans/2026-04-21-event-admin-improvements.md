# Event-Admin Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make event-admin production-ready by fixing security issues, enforcing read-only guarantees, improving data integrity, and adding observability.

**Architecture:** Five phases of targeted improvements to the existing layered architecture. No new layers or services. Changes touch middleware, config, auth, adapters, DTOs, schemas, routes, and logger.

**Tech Stack:** Python 3.14, FastAPI, Dishka, structlog, SQLAlchemy async, PyJWT, Pydantic

---

## Task 1: Fix Python 2 except syntax in middleware

**Files:**
- Modify: `event_admin/middleware.py:44`

- [ ] **Step 1: Fix the except clause**

In `event_admin/middleware.py`, line 44, replace:

```python
        except jwt.InvalidTokenError, KeyError:
```

with:

```python
        except (jwt.InvalidTokenError, KeyError):
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "import ast; ast.parse(open('event_admin/middleware.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add event_admin/middleware.py
git commit -m "fix: correct Python 2 except syntax in JWT middleware"
```

---

## Task 2: Inject Settings into middleware via constructor

**Files:**
- Modify: `event_admin/middleware.py:11,21-28`
- Modify: `event_admin/main.py:45-46`

- [ ] **Step 1: Update middleware to accept settings in constructor**

In `event_admin/middleware.py`, replace the import and `__init__`/`dispatch` to accept settings:

Remove the import line:
```python
from event_admin.auth import _get_settings
```

Replace `__init__` with:
```python
    def __init__(self, app: ASGIApp, settings: Settings, public_paths: frozenset[str] = frozenset()) -> None:
        super().__init__(app)
        self._settings = settings
        self._public_paths = public_paths
```

Add the import:
```python
from event_admin.config import Settings
```

In `dispatch`, replace:
```python
        settings = _get_settings()
```
with:
```python
        settings = self._settings
```

- [ ] **Step 2: Update main.py to pass settings to middleware**

In `event_admin/main.py`, replace lines 45-46:
```python
app.add_middleware(JWTAuthMiddleware, public_paths=frozenset({"/auth/login", "/health"}))
_settings = Settings()
```

with:
```python
_settings = Settings()
app.add_middleware(JWTAuthMiddleware, settings=_settings, public_paths=frozenset({"/auth/login", "/health"}))
```

- [ ] **Step 3: Verify import works**

Run: `python -c "from event_admin.middleware import JWTAuthMiddleware; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add event_admin/middleware.py event_admin/main.py
git commit -m "refactor: inject Settings into JWTAuthMiddleware via constructor"
```

---

## Task 3: Consolidate JWT validation — middleware stores payload in request.state

**Files:**
- Modify: `event_admin/middleware.py:39-47`
- Modify: `event_admin/auth.py:14,22-25,37-57`

- [ ] **Step 1: Store decoded payload in request.state in middleware**

In `event_admin/middleware.py`, replace the token decoding block (lines 39-45, after the syntax fix from Task 1):

```python
        token = auth_header[7:]
        try:
            jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        except jwt.ExpiredSignatureError:
            return JSONResponse({"detail": "Token expired"}, status_code=401)
        except (jwt.InvalidTokenError, KeyError):
            return JSONResponse({"detail": "Invalid token"}, status_code=401)

        return await call_next(request)
```

with:

```python
        token = auth_header[7:]
        try:
            payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
            request.state.user_payload = {"sub": payload["sub"], "role": payload["role"]}
        except jwt.ExpiredSignatureError:
            return JSONResponse({"detail": "Token expired"}, status_code=401)
        except (jwt.InvalidTokenError, KeyError):
            return JSONResponse({"detail": "Invalid token"}, status_code=401)

        return await call_next(request)
```

- [ ] **Step 2: Simplify get_current_user to read from request.state**

In `event_admin/auth.py`, replace `get_current_user` and remove unused imports:

Remove `bearer_scheme` (line 14):
```python
bearer_scheme = HTTPBearer(auto_error=False)
```

Remove `_get_settings` function (lines 22-24):
```python
@lru_cache(maxsize=1)
def _get_settings() -> Settings:
    return Settings()
```

Remove now-unused imports: `lru_cache`, `jwt`, `HTTPAuthorizationCredentials`, `HTTPBearer`, `Settings`.

Replace `get_current_user`:
```python
def get_current_user(request: Request) -> TokenPayload:
    payload = getattr(request.state, "user_payload", None)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return TokenPayload(sub=payload["sub"], role=payload["role"])
```

Add import:
```python
from starlette.requests import Request
```

The full `auth.py` after changes:
```python
from __future__ import annotations
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from pydantic import BaseModel
from starlette.requests import Request

from event_admin.config import Settings


class TokenPayload(BaseModel):
    sub: str  # email
    role: str  # "admin" | "user"


@lru_cache(maxsize=1)
def _get_settings() -> Settings:
    return Settings()


def create_access_token(email: str, role: str) -> str:
    settings = _get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {"sub": email, "role": role, "exp": expire},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def get_current_user(request: Request) -> TokenPayload:
    payload = getattr(request.state, "user_payload", None)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return TokenPayload(sub=payload["sub"], role=payload["role"])


def require_admin(user: Annotated[TokenPayload, Depends(get_current_user)]) -> TokenPayload:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
```

Note: `_get_settings` and `lru_cache` and `jwt` are still needed for `create_access_token`.

- [ ] **Step 3: Verify imports**

Run: `python -c "from event_admin.auth import get_current_user, create_access_token, require_admin; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add event_admin/middleware.py event_admin/auth.py
git commit -m "refactor: consolidate JWT validation — decode once in middleware, read from request.state"
```

---

## Task 4: Fix CORS — use configurable origins from Settings

**Files:**
- Modify: `event_admin/main.py:47-53`

Note: `cors_origins` already exists in `config.py` as `cors_origins: list[str] = Field(default=["http://localhost:5173"])`. The `main.py` already uses `_settings.cors_origins` (line 49). This is already correct after Task 2 changes. Verify and skip if already done.

- [ ] **Step 1: Verify CORS uses settings**

After Task 2, `main.py` creates `_settings = Settings()` before middleware registration. Line 49 already uses `_settings.cors_origins`. Confirm this is the case by reading the file after Task 2 changes.

If for any reason `allow_origins=["*"]` is still present, replace with `allow_origins=_settings.cors_origins`.

- [ ] **Step 2: Commit (if changes were needed)**

```bash
git add event_admin/main.py
git commit -m "fix: use configurable CORS origins from settings"
```

---

## Task 5: Add auth audit logging to login endpoint

**Files:**
- Modify: `event_admin/routes.py:39-55`

- [ ] **Step 1: Add granular logging to login**

Replace the login function body in `event_admin/routes.py` (lines 46-55):

```python
    user = await db.get_by_email(body.email)
    if (
        user is None
        or not user["is_active"]
        or not password_service.verify(body.password, user["hashed_password"])
        or not totp_service.verify(body.totp_code, user["totp_secret"])
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(email=user["email"], role=user["role"])
    return LoginResponse(access_token=token, role=user["role"])
```

with:

```python
    user = await db.get_by_email(body.email)
    if user is None:
        logger.warning("login_failed", email=body.email, reason="user_not_found")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user["is_active"]:
        logger.warning("login_failed", email=body.email, reason="user_inactive")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not password_service.verify(body.password, user["hashed_password"]):
        logger.warning("login_failed", email=body.email, reason="bad_password")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not totp_service.verify(body.totp_code, user["totp_secret"]):
        logger.warning("login_failed", email=body.email, reason="bad_totp")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(email=user["email"], role=user["role"])
    logger.info("login_success", email=user["email"], role=user["role"])
    return LoginResponse(access_token=token, role=user["role"])
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "import ast; ast.parse(open('event_admin/routes.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add event_admin/routes.py
git commit -m "feat: add audit logging for login success and failure"
```

---

## Task 6: Remove write methods from ISqlExecutor and SqlExecutor

**Files:**
- Modify: `event_admin/interfaces/sql.py`
- Modify: `event_admin/adapters/sql.py`

- [ ] **Step 1: Verify no callers use write methods**

Run: `grep -rn "\.execute\b\|execute_in_transaction" event_admin/ --include="*.py" | grep -v "sql.py" | grep -v "interfaces/sql.py"`

Expected: No matches (only `fetch_one` and `fetch_all` are used by adapters).

- [ ] **Step 2: Confirm interfaces/sql.py only has fetch methods**

The current `interfaces/sql.py` already contains only `fetch_one` and `fetch_all` in `ISqlExecutor`. The current `adapters/sql.py` already contains only `fetch_one` and `fetch_all`. No changes needed — the write methods were already removed or never existed in the current code.

If `execute` or `execute_in_transaction` exist, remove them from both files.

- [ ] **Step 3: Commit (if changes were needed)**

```bash
git add event_admin/interfaces/sql.py event_admin/adapters/sql.py
git commit -m "refactor: remove write methods from SqlExecutor — enforce read-only"
```

---

## Task 7: Replace list with tuple in frozen DTOs

**Files:**
- Modify: `event_admin/dto/bookings.py:115`
- Modify: `event_admin/adapters/bookings_db.py:252`

- [ ] **Step 1: Check which DTO fields use list**

The DTOs in `dto/bookings.py` already use `tuple[..., ...]` for all collection fields. The only mutable collection is the intermediate `list` used in `status_history_by_notification` dict values in `bookings_db.py:252` — but these are converted to `tuple()` at construction time (line 292).

Verify: `grep -n "list\[" event_admin/dto/bookings.py`
Expected: No matches — all collections are already `tuple`.

The `BookingVideoEventItemDto.payload` field is `dict[str, Any]` (line 115) — this is mutable but represents a JSON payload that should remain a dict for serialization compatibility. Leave as-is.

- [ ] **Step 2: Check response schemas for list fields**

In `schemas/bookings.py`, response models use `list[...]` for nested collections (lines 122, 211-216, 256). This is correct for Pydantic response models — they serialize from any iterable and `list` is the standard JSON array type.

No changes needed for DTOs or schemas.

- [ ] **Step 3: Commit (skip if no changes)**

No commit needed — DTOs already use tuples.

---

## Task 8: Add BookingStatus enum for current_statuses validation

**Files:**
- Create: `event_admin/enums.py`
- Modify: `event_admin/dto/bookings.py:1-4,9`
- Modify: `event_admin/routes.py:65-66`
- Modify: `event_admin/schemas/bookings.py:37,207`

- [ ] **Step 1: Determine known booking statuses**

Run: `grep -rn "current_status" event_admin/ --include="*.py" | head -20`

Check the SQL queries and filter usage. The statuses come from the database (written by event-saver). Common statuses based on the bounce query: booking lifecycle statuses. Check event-saver's schema or event-schemas for the canonical list.

Run: `grep -rn "BookingStatus\|booking_status\|BOOKING_STATUS" ../event-saver/ ../event-schemas/ --include="*.py" 2>/dev/null | head -20`

- [ ] **Step 2: Create enums.py with BookingStatus**

Create `event_admin/enums.py`:

```python
from enum import StrEnum


class BookingStatus(StrEnum):
    CREATED = "created"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"
```

Adjust values based on what Step 1 reveals from the database/event-saver. If no canonical list is found, use these as the starting set and keep the query filter accepting `str` with a comment noting validation is best-effort.

- [ ] **Step 3: Use enum in route query parameter**

In `event_admin/routes.py`, change line 66:

```python
    current_statuses: Annotated[list[str] | None, Query()] = None,
```

to:

```python
    current_statuses: Annotated[list[BookingStatus] | None, Query()] = None,
```

Add import:
```python
from event_admin.enums import BookingStatus
```

- [ ] **Step 4: Use enum in BookingDetailsResponse and BookingListItemResponse**

In `event_admin/schemas/bookings.py`, change `current_status: str | None` to `current_status: str | None` — keep as `str` in response schemas since the DB may contain values not in our enum. The enum is for input validation only.

No schema changes needed.

- [ ] **Step 5: Verify syntax**

Run: `python -c "import ast; ast.parse(open('event_admin/enums.py').read()); ast.parse(open('event_admin/routes.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add event_admin/enums.py event_admin/routes.py
git commit -m "feat: add BookingStatus enum for input validation on current_statuses filter"
```

---

## Task 9: Add missing timestamp fields to BookingDetailsResponse

**Files:**
- Modify: `event_admin/schemas/bookings.py:202-245`

- [ ] **Step 1: Add first_seen_at, last_seen_at, updated_at to BookingDetailsResponse**

In `event_admin/schemas/bookings.py`, add the missing fields to `BookingDetailsResponse` class (after line 204):

```python
class BookingDetailsResponse(BaseModel):
    id: int
    booking_uid: str
    first_seen_at: datetime
    last_seen_at: datetime
    start_time: datetime | None
    end_time: datetime | None
    current_status: str | None
    created_at: datetime
    updated_at: datetime
    current_organizer_participant: ParticipantResponse | None
    current_client_participant: ParticipantResponse | None
    organizer_history: list[BookingOrganizerHistoryItemResponse]
    meeting_links: list[BookingMeetingLinkItemResponse]
    email_notifications: list[BookingEmailNotificationItemResponse]
    telegram_notifications: list[BookingTelegramNotificationItemResponse]
    chat_events: list[BookingChatEventItemResponse]
    video_events: list[BookingVideoEventItemResponse]
```

- [ ] **Step 2: Update from_dto to map the new fields**

In `from_dto`, add the three fields to the constructor call:

```python
    @classmethod
    def from_dto(cls, dto: BookingDetailsDto) -> BookingDetailsResponse:
        return cls(
            id=dto.id,
            booking_uid=dto.booking_uid,
            first_seen_at=dto.first_seen_at,
            last_seen_at=dto.last_seen_at,
            start_time=dto.start_time,
            end_time=dto.end_time,
            current_status=dto.current_status,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
            current_organizer_participant=(
                ParticipantResponse.from_dto(dto.current_organizer_participant)
                if dto.current_organizer_participant
                else None
            ),
            current_client_participant=(
                ParticipantResponse.from_dto(dto.current_client_participant) if dto.current_client_participant else None
            ),
            organizer_history=[BookingOrganizerHistoryItemResponse.from_dto(item) for item in dto.organizer_history],
            meeting_links=[BookingMeetingLinkItemResponse.from_dto(item) for item in dto.meeting_links],
            email_notifications=[
                BookingEmailNotificationItemResponse.from_dto(item) for item in dto.email_notifications
            ],
            telegram_notifications=[
                BookingTelegramNotificationItemResponse.from_dto(item) for item in dto.telegram_notifications
            ],
            chat_events=[BookingChatEventItemResponse.from_dto(item) for item in dto.chat_events],
            video_events=[BookingVideoEventItemResponse.from_dto(item) for item in dto.video_events],
        )
```

- [ ] **Step 3: Verify syntax**

Run: `python -c "import ast; ast.parse(open('event_admin/schemas/bookings.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add event_admin/schemas/bookings.py
git commit -m "fix: add missing timestamp fields to BookingDetailsResponse"
```

---

## Task 10: Add request correlation ID middleware

**Files:**
- Modify: `event_admin/middleware.py`
- Modify: `event_admin/main.py`

- [ ] **Step 1: Add request ID generation to JWTAuthMiddleware**

In `event_admin/middleware.py`, add imports at the top:

```python
import uuid

import structlog.contextvars
```

At the beginning of the `dispatch` method (before the debug check), add:

```python
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        structlog.contextvars.bind_contextvars(request_id=request_id)
```

Before each `return` statement in `dispatch` (both success and error paths), the response needs the header. Restructure dispatch to always add the header:

Full updated `dispatch` method:

```python
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Coroutine[Any, Any, Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        structlog.contextvars.bind_contextvars(request_id=request_id)

        if self._settings.debug:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        if request.method == "OPTIONS" or request.url.path in self._public_paths:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse({"detail": "Missing bearer token"}, status_code=401, headers={"X-Request-ID": request_id})

        token = auth_header[7:]
        try:
            payload = jwt.decode(token, self._settings.jwt_secret_key, algorithms=[self._settings.jwt_algorithm])
            request.state.user_payload = {"sub": payload["sub"], "role": payload["role"]}
        except jwt.ExpiredSignatureError:
            return JSONResponse({"detail": "Token expired"}, status_code=401, headers={"X-Request-ID": request_id})
        except (jwt.InvalidTokenError, KeyError):
            return JSONResponse({"detail": "Invalid token"}, status_code=401, headers={"X-Request-ID": request_id})

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        structlog.contextvars.clear_contextvars()
        return response
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "import ast; ast.parse(open('event_admin/middleware.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add event_admin/middleware.py
git commit -m "feat: add request correlation ID to all responses and structured logs"
```

---

## Task 11: Remove dead logger suppressions

**Files:**
- Modify: `event_admin/logger.py:72-75`

- [ ] **Step 1: Remove unused logger suppressions**

In `event_admin/logger.py`, remove lines 72-75:

```python
    logging.getLogger("aiokafka").setLevel(logging.ERROR)
    logging.getLogger("asyncio_redis").setLevel(logging.ERROR)
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("botocore").setLevel(logging.ERROR)
```

Keep only `httpcore` (used by httpx, which is a real dependency):

```python
    logging.getLogger("httpcore").setLevel(logging.ERROR)
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "import ast; ast.parse(open('event_admin/logger.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add event_admin/logger.py
git commit -m "cleanup: remove logger suppressions for unused dependencies"
```

---

## Task 12: Add booking_uids length validation

**Files:**
- Modify: `event_admin/routes.py:65`

- [ ] **Step 1: Add max_length constraint to booking_uids**

In `event_admin/routes.py`, replace line 65:

```python
    booking_uids: Annotated[list[str] | None, Query()] = None,
```

with:

```python
    booking_uids: Annotated[list[Annotated[str, Query(max_length=100)]] | None, Query(max_length=200)] = None,
```

Note: FastAPI/Pydantic v2 uses `Annotated` with `Query` for nested validation. If this doesn't work due to FastAPI limitations on nested Query, use a simpler approach — add a guard at the top of the function:

```python
    if booking_uids and len(booking_uids) > 200:
        raise HTTPException(status_code=400, detail="Too many booking_uids (max 200)")
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "import ast; ast.parse(open('event_admin/routes.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add event_admin/routes.py
git commit -m "fix: add length validation for booking_uids query parameter"
```

---

## Task 13: Add OpenAPI descriptions to all endpoints

**Files:**
- Modify: `event_admin/routes.py`

- [ ] **Step 1: Add summary and description to each route**

Update each route decorator:

```python
@root_router.get("/health", summary="Health check", description="Returns service health status.")
```

```python
@root_router.post("/auth/login", response_model=LoginResponse, summary="Admin login", description="Authenticate with email, password, and TOTP code. Returns a JWT access token.")
```

```python
@root_router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Logout", description="Client-side logout. No server-side token revocation.")
```

```python
@bookings_router.get("", response_model=list[BookingListItemResponse], summary="List bookings", description="List bookings with optional filters by UID, status, organizer, or client.")
```

```python
@bookings_router.get("/future-email-bounced", response_model=list[BookingFutureBouncedEmailItemResponse], summary="List future email-bounced bookings", description="List future bookings that have email bounce notifications.")
```

```python
@bookings_router.get("/{booking_uid}", response_model=BookingDetailsResponse, summary="Get booking details", description="Get full booking details including notifications, meeting links, and event history.")
```

```python
@users_router.get("", summary="List users", description="Proxy to event-users service. List users with optional email/role filters.")
```

```python
@users_router.get("/id/{user_id}", summary="Get user by ID", description="Proxy to event-users service. Get a single user by UUID.")
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "import ast; ast.parse(open('event_admin/routes.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add event_admin/routes.py
git commit -m "docs: add OpenAPI summaries and descriptions to all endpoints"
```

---

## Task 14: Run linter and format

**Files:**
- All modified files

- [ ] **Step 1: Run ruff check and format**

```bash
ruff check --fix .
ruff format .
```

- [ ] **Step 2: Fix any remaining lint errors manually**

Address any errors that `--fix` couldn't auto-resolve.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "style: apply ruff linting and formatting"
```

---

## Task 15: Update service documentation

**Files:**
- Modify: `docs/SERVICE_OVERVIEW.md`
- Modify: `docs/API_CONTRACTS.md`
- Modify: `docs/AUDIT.md`

- [ ] **Step 1: Update SERVICE_OVERVIEW.md**

Add/update the "Known Issues" section to mark resolved items:
- ~~Python 2 except syntax~~ (fixed)
- ~~Settings re-instantiation per request~~ (fixed)
- ~~Double JWT decode~~ (fixed)
- ~~Missing auth audit logging~~ (fixed)
- ~~Missing request correlation ID~~ (fixed)

- [ ] **Step 2: Update API_CONTRACTS.md**

Document the new fields added to `BookingDetailsResponse`:
- `first_seen_at: datetime`
- `last_seen_at: datetime`
- `updated_at: datetime`

Document the `BookingStatus` enum values accepted by `current_statuses` filter.

Document the `X-Request-ID` response header.

- [ ] **Step 3: Update AUDIT.md**

Mark resolved audit findings with status "FIXED" and the date.

- [ ] **Step 4: Commit**

```bash
git add docs/
git commit -m "docs: update service docs to reflect improvements"
```
