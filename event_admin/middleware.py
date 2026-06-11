from __future__ import annotations
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import jwt
import structlog.contextvars
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from event_admin.config import Settings


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Validates JWT for every request except those in *public_paths*.

    OPTIONS requests are always passed through so CORS preflight works
    regardless of middleware ordering.

    There is intentionally NO debug bypass: authentication is enforced
    identically in every environment (audit-v2 CRITICAL finding).
    """

    def __init__(self, app: ASGIApp, settings: Settings, public_paths: frozenset[str] = frozenset()) -> None:
        super().__init__(app)
        self._settings = settings
        self._public_paths = public_paths

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Coroutine[Any, Any, Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        structlog.contextvars.bind_contextvars(request_id=request_id)

        try:
            return await self._handle(request, call_next, request_id)
        finally:
            structlog.contextvars.clear_contextvars()

    def _decode_token(self, token: str) -> dict[str, Any]:
        """Decode and verify the JWT, honoring optional aud/iss binding.

        When jwt_audience is unset, tokens carrying an aud claim must still
        pass (rollout tolerance, mirrored in event-users).
        """
        settings = self._settings
        kwargs: dict[str, Any] = {"options": {"verify_aud": bool(settings.jwt_audience)}}
        if settings.jwt_audience:
            kwargs["audience"] = settings.jwt_audience
        if settings.jwt_issuer:
            kwargs["issuer"] = settings.jwt_issuer
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            **kwargs,
        )

    async def _handle(
        self,
        request: Request,
        call_next: Callable[[Request], Coroutine[Any, Any, Response]],
        request_id: str,
    ) -> Response:
        if request.method == "OPTIONS" or request.url.path in self._public_paths:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"detail": "Missing bearer token"},
                status_code=401,
                headers={"X-Request-ID": request_id},
            )

        token = auth_header[7:]
        try:
            payload = self._decode_token(token)
            request.state.user_payload = {"sub": payload["sub"], "role": payload["role"]}
        except jwt.ExpiredSignatureError:
            return JSONResponse({"detail": "Token expired"}, status_code=401, headers={"X-Request-ID": request_id})
        except jwt.InvalidTokenError, KeyError:
            return JSONResponse({"detail": "Invalid token"}, status_code=401, headers={"X-Request-ID": request_id})

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
