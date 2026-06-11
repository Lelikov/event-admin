"""POST /api/users/cache/invalidate: token-gated, constant-time comparison."""

import inspect
import uuid

from event_admin.routes import invalidate_users_cache


async def test_invalidate_with_valid_token(client, settings, fakes) -> None:
    user_id = uuid.uuid4()
    fakes.users_cache.set_user(user_id, {"id": str(user_id)})

    response = await client.post(
        "/api/users/cache/invalidate",
        headers={"Authorization": f"Bearer {settings.cache_invalidation_token}"},
    )

    assert response.status_code == 204
    assert fakes.users_cache.get_user(user_id) is None


async def test_invalidate_with_wrong_token_is_rejected(client, fakes) -> None:
    user_id = uuid.uuid4()
    fakes.users_cache.set_user(user_id, {"id": str(user_id)})

    response = await client.post(
        "/api/users/cache/invalidate",
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 401
    assert fakes.users_cache.get_user(user_id) is not None


async def test_invalidate_without_bearer_scheme_is_rejected(client, settings) -> None:
    response = await client.post(
        "/api/users/cache/invalidate",
        headers={"Authorization": settings.cache_invalidation_token},
    )
    assert response.status_code == 401


def test_route_uses_constant_time_comparison() -> None:
    """Regression guard: the handler must compare via hmac.compare_digest."""
    source = inspect.getsource(invalidate_users_cache)
    assert "hmac.compare_digest" in source
