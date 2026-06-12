"""Tests for the /health (liveness) and /ready (readiness) endpoints."""

from sqlalchemy.exc import OperationalError


class TestHealth:
    async def test_health_is_public_and_shallow(self, client) -> None:
        response = await client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestReady:
    async def test_ready_is_public_when_database_reachable(self, client) -> None:
        response = await client.get("/ready")

        assert response.status_code == 200
        assert response.json() == {"status": "ready", "checks": {"database": True}}

    async def test_not_ready_when_database_down(self, client, fakes) -> None:
        fakes.engine.connect_error = OperationalError("select 1", {}, Exception("connection refused"))

        response = await client.get("/ready")

        assert response.status_code == 503
        assert response.json() == {"status": "not_ready", "checks": {"database": False}}
