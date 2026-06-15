"""Tests for /api/notifications/* proxy routes to event-notifier."""

import httpx
import pytest


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_upstream_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "http://notifier.test/api/notifications/config")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError("upstream error", request=request, response=response)


# ── require_admin gate ────────────────────────────────────────────────────────


async def test_get_config_without_token_returns_401(client) -> None:
    response = await client.get("/api/notifications/config")
    assert response.status_code == 401


async def test_put_config_without_token_returns_401(client) -> None:
    response = await client.put(
        "/api/notifications/config/BOOKING_CREATED/email",
        json={"enabled": True},
    )
    assert response.status_code == 401


async def test_unisender_templates_without_token_returns_401(client) -> None:
    response = await client.get("/api/notifications/unisender-templates")
    assert response.status_code == 401


async def test_telegram_preview_without_token_returns_401(client) -> None:
    response = await client.post(
        "/api/notifications/telegram/preview",
        json={"telegram_body": "hi"},
    )
    assert response.status_code == 401


# ── pass-through 200 ──────────────────────────────────────────────────────────


async def test_get_config_returns_upstream_response(client, admin_headers, fakes) -> None:
    fakes.notifier_client.config_response = {
        "bindings": [
            {
                "trigger_event": "BOOKING_CREATED",
                "channel": "email",
                "enabled": True,
                "unisender_template_id": "uuid-1",
                "telegram_body": None,
            }
        ]
    }

    response = await client.get("/api/notifications/config", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["bindings"][0]["trigger_event"] == "BOOKING_CREATED"


async def test_put_config_returns_ok(client, admin_headers, fakes) -> None:
    response = await client.put(
        "/api/notifications/config/BOOKING_CREATED/email",
        json={"enabled": False, "unisender_template_id": None},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_unisender_templates_returns_list(client, admin_headers, fakes) -> None:
    fakes.notifier_client.templates_response = {
        "templates": [{"id": "uuid-1", "name": "Welcome"}]
    }

    response = await client.get("/api/notifications/unisender-templates", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["templates"][0]["name"] == "Welcome"


async def test_telegram_preview_returns_rendered(client, admin_headers, fakes) -> None:
    fakes.notifier_client.preview_response = {"rendered": "Привет, Иван!"}

    response = await client.post(
        "/api/notifications/telegram/preview",
        json={"telegram_body": "Привет, {{ client_name }}!"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["rendered"] == "Привет, Иван!"


# ── error mapping ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("status_code", [400, 404, 422, 500, 503])
async def test_upstream_error_is_mapped_to_structured_error(
    client, admin_headers, fakes, status_code: int
) -> None:
    fakes.notifier_client.error = _make_upstream_error(status_code)

    response = await client.get("/api/notifications/config", headers=admin_headers)

    assert response.status_code == status_code
    detail = response.json()["detail"]
    assert detail["code"] == "notifier_service_error"
    assert str(status_code) in detail["message"]


async def test_upstream_error_on_put_is_mapped(client, admin_headers, fakes) -> None:
    fakes.notifier_client.error = _make_upstream_error(400)

    response = await client.put(
        "/api/notifications/config/BOOKING_CREATED/telegram",
        json={"enabled": True, "telegram_body": "{% bad jinja"},
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "notifier_service_error"


# ── non-admin JWT is rejected ─────────────────────────────────────────────────


async def test_user_role_cannot_access_notifications(client, user_headers) -> None:
    response = await client.get("/api/notifications/config", headers=user_headers)
    assert response.status_code == 403
