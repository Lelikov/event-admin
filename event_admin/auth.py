from __future__ import annotations
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from pydantic import BaseModel
from starlette.requests import Request

from event_admin.config import Settings


class TokenPayload(BaseModel):
    sub: str  # email
    role: str  # "admin" | "user"


def create_access_token(settings: Settings, *, email: str, role: str) -> str:
    """Mint an HS256 access token; adds aud/iss claims when configured."""
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    claims: dict[str, Any] = {"sub": email, "role": role, "exp": expire}
    if settings.jwt_audience:
        claims["aud"] = settings.jwt_audience
    if settings.jwt_issuer:
        claims["iss"] = settings.jwt_issuer
    return jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


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
