"""JWTAuthMiddleware: auth is enforced in every environment (no debug bypass)."""

import datetime as dt

import jwt
from httpx import ASGITransport, AsyncClient

from event_admin.auth import create_access_token
from event_admin.main import create_app
from tests.conftest import FakeProvider, make_settings


async def test_request_without_token_is_rejected(client) -> None:
    response = await client.get("/bookings")
    assert response.status_code == 401
    assert response.json() == {"detail": "Missing bearer token"}


async def test_request_with_invalid_token_is_rejected(client) -> None:
    response = await client.get("/bookings", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid token"}


async def test_request_with_wrong_signature_is_rejected(client, settings) -> None:
    other = make_settings(jwt_secret_key="another-secret-key-0123456789ab")
    token = create_access_token(other, email="admin@test.local", role="admin")
    response = await client.get("/bookings", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


async def test_expired_token_is_rejected(client, settings) -> None:
    expired = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=5)
    token = jwt.encode(
        {"sub": "admin@test.local", "role": "admin", "exp": expired},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    response = await client.get("/bookings", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Token expired"}


async def test_valid_token_passes(client, admin_headers) -> None:
    response = await client.get("/bookings", headers=admin_headers)
    assert response.status_code == 200


async def test_non_admin_role_gets_403(client, user_headers) -> None:
    response = await client.get("/bookings", headers=user_headers)
    assert response.status_code == 403


async def test_debug_true_does_not_bypass_auth(settings, fakes) -> None:
    """CRITICAL audit-v2 regression guard: DEBUG must never disable authentication."""
    debug_settings = make_settings(debug=True)
    app = create_app(debug_settings, provider=FakeProvider(debug_settings, fakes))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/bookings")
    assert response.status_code == 401


async def test_options_passes_without_token(client) -> None:
    response = await client.options("/bookings")
    assert response.status_code != 401


async def test_response_carries_request_id(client, admin_headers) -> None:
    response = await client.get("/bookings", headers={**admin_headers, "X-Request-ID": "req-42"})
    assert response.headers["X-Request-ID"] == "req-42"
