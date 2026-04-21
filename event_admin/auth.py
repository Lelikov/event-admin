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
