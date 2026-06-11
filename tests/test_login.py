"""POST /auth/login: credential matrix, lockout, and TOTP replay protection."""

import binascii

import pyotp
import pytest

from event_admin.services.totp import TOTPService


LOGIN = {"email": "admin@example.com", "password": "correct-password", "totp_code": "123456"}


@pytest.fixture
def admin_user(fakes) -> dict:
    fakes.admin_db.add_user("admin@example.com")
    return fakes.admin_db.users["admin@example.com"]


async def test_login_success_returns_token(client, admin_user) -> None:
    response = await client.post("/auth/login", json=LOGIN)
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "admin"
    assert body["access_token"]


async def test_login_unknown_user_401(client) -> None:
    response = await client.post("/auth/login", json=LOGIN)
    assert response.status_code == 401
    assert response.json()["detail"] == {"code": "invalid_credentials", "message": "Invalid credentials"}


async def test_login_inactive_user_401(client, fakes) -> None:
    fakes.admin_db.add_user("admin@example.com", is_active=False)
    response = await client.post("/auth/login", json=LOGIN)
    assert response.status_code == 401


async def test_login_bad_password_401(client, admin_user) -> None:
    response = await client.post("/auth/login", json={**LOGIN, "password": "wrong"})
    assert response.status_code == 401


async def test_login_bad_totp_401(client, admin_user) -> None:
    response = await client.post("/auth/login", json={**LOGIN, "totp_code": "000000"})
    assert response.status_code == 401


async def test_login_lockout_after_repeated_failures(client, admin_user) -> None:
    for _ in range(5):
        response = await client.post("/auth/login", json={**LOGIN, "password": "wrong"})
        assert response.status_code == 401

    # Even correct credentials are now rejected with 429 for this IP+email
    response = await client.post("/auth/login", json=LOGIN)
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "too_many_login_attempts"


async def test_totp_code_cannot_be_replayed(client, admin_user) -> None:
    first = await client.post("/auth/login", json=LOGIN)
    assert first.status_code == 200

    replay = await client.post("/auth/login", json=LOGIN)
    assert replay.status_code == 401


async def test_successful_login_resets_failure_counter(client, admin_user, fakes) -> None:
    for _ in range(3):
        await client.post("/auth/login", json={**LOGIN, "password": "wrong"})

    response = await client.post("/auth/login", json=LOGIN)
    assert response.status_code == 200

    # counter was reset: three more failures do not lock the account
    for _ in range(3):
        response = await client.post("/auth/login", json={**LOGIN, "password": "wrong"})
        assert response.status_code == 401


def test_totp_service_malformed_secret_fails_closed() -> None:
    service = TOTPService()
    assert service.verify("123456", "not-base32-!!!") is False
    assert service.verify("123456", "") is False


def test_totp_service_accepts_valid_code() -> None:
    service = TOTPService()
    secret = service.generate_secret()
    code = pyotp.TOTP(secret).now()
    assert service.verify(code, secret) is True


def test_malformed_secret_raises_without_guard() -> None:
    """Documents why the try/except exists: pyotp raises on bad base32."""
    with pytest.raises((binascii.Error, ValueError)):
        pyotp.TOTP("not-base32-!!!").verify("123456")
