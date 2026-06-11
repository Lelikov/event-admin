"""JWT lifetime and optional aud/iss binding (coordination with event-users)."""

import datetime as dt

import jwt
from httpx import ASGITransport, AsyncClient

from event_admin.auth import create_access_token
from event_admin.main import create_app
from tests.conftest import FakeProvider, make_settings


AUD = "event-admin-api"
ISS = "event-admin"


def test_default_expiry_is_one_hour(settings) -> None:
    token = create_access_token(settings, email="a@example.com", role="admin")
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
    lifetime = payload["exp"] - dt.datetime.now(dt.UTC).timestamp()
    assert lifetime <= 60 * 60 + 5
    assert lifetime > 55 * 60


def test_token_has_no_aud_iss_when_unconfigured(settings) -> None:
    token = create_access_token(settings, email="a@example.com", role="admin")
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
    assert "aud" not in payload
    assert "iss" not in payload


def test_token_carries_aud_iss_when_configured() -> None:
    settings = make_settings(jwt_audience=AUD, jwt_issuer=ISS)
    token = create_access_token(settings, email="a@example.com", role="admin")
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"], audience=AUD, issuer=ISS)
    assert payload["aud"] == AUD
    assert payload["iss"] == ISS


async def _request_with(settings, fakes, token: str) -> int:
    app = create_app(settings, provider=FakeProvider(settings, fakes))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/bookings", headers={"Authorization": f"Bearer {token}"})
    return response.status_code


async def test_bound_app_rejects_token_without_aud(fakes) -> None:
    bound = make_settings(jwt_audience=AUD, jwt_issuer=ISS)
    unbound = make_settings()
    token = create_access_token(unbound, email="a@example.com", role="admin")
    assert await _request_with(bound, fakes, token) == 401


async def test_bound_app_accepts_matching_token(fakes) -> None:
    bound = make_settings(jwt_audience=AUD, jwt_issuer=ISS)
    token = create_access_token(bound, email="a@example.com", role="admin")
    assert await _request_with(bound, fakes, token) == 200


async def test_unbound_app_tolerates_token_with_aud_iss(fakes) -> None:
    """Rollout tolerance: extra aud/iss claims must still pass when unset."""
    bound = make_settings(jwt_audience=AUD, jwt_issuer=ISS)
    unbound = make_settings()
    token = create_access_token(bound, email="a@example.com", role="admin")
    assert await _request_with(unbound, fakes, token) == 200
