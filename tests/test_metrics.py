"""/metrics endpoint, HTTP RED middleware, login and blacklist counters (through the real app)."""

from prometheus_client import REGISTRY

from tests.test_login import LOGIN


def _sample(name: str, labels: dict[str, str]) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


class TestMetricsEndpoint:
    async def test_metrics_returns_prometheus_exposition_without_auth(self, client) -> None:
        response = await client.get("/metrics")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert "http_requests_total" in response.text


class TestHttpRedMiddleware:
    async def test_login_request_counted_by_route_template(self, client, fakes) -> None:
        fakes.admin_db.add_user(LOGIN["email"])
        labels = {"method": "POST", "route": "/auth/login", "status": "200"}
        before = _sample("http_requests_total", labels)
        duration_before = _sample("http_request_duration_seconds_count", {"method": "POST", "route": "/auth/login"})

        response = await client.post("/auth/login", json=LOGIN)

        assert response.status_code == 200
        assert _sample("http_requests_total", labels) == before + 1
        assert (
            _sample("http_request_duration_seconds_count", {"method": "POST", "route": "/auth/login"})
            == duration_before + 1
        )

    async def test_health_and_metrics_excluded(self, client) -> None:
        await client.get("/health")
        await client.get("/metrics")

        assert _sample("http_requests_total", {"method": "GET", "route": "/health", "status": "200"}) == 0.0
        assert _sample("http_requests_total", {"method": "GET", "route": "/metrics", "status": "200"}) == 0.0

    async def test_unauthenticated_request_recorded_as_unmatched(self, client) -> None:
        labels = {"method": "GET", "route": "unmatched", "status": "401"}
        before = _sample("http_requests_total", labels)

        response = await client.get("/bookings")

        assert response.status_code == 401
        assert _sample("http_requests_total", labels) == before + 1


class TestLoginCounter:
    async def test_success_increments(self, client, fakes) -> None:
        fakes.admin_db.add_user(LOGIN["email"])
        before = _sample("admin_logins_total", {"outcome": "success"})

        response = await client.post("/auth/login", json=LOGIN)

        assert response.status_code == 200
        assert _sample("admin_logins_total", {"outcome": "success"}) == before + 1

    async def test_failure_increments(self, client, fakes) -> None:
        fakes.admin_db.add_user(LOGIN["email"])
        before = _sample("admin_logins_total", {"outcome": "failure"})

        response = await client.post("/auth/login", json={**LOGIN, "password": "wrong"})

        assert response.status_code == 401
        assert _sample("admin_logins_total", {"outcome": "failure"}) == before + 1


class TestBlacklistOpsCounter:
    async def test_create_increments(self, client, admin_headers) -> None:
        before = _sample("admin_blacklist_ops_total", {"op": "create"})

        response = await client.post(
            "/api/blacklist",
            json={"field": "client_email", "value": "Spammer@Example.com"},
            headers=admin_headers,
        )

        assert response.status_code == 201
        assert _sample("admin_blacklist_ops_total", {"op": "create"}) == before + 1

    async def test_delete_increments(self, client, admin_headers) -> None:
        created = await client.post(
            "/api/blacklist",
            json={"field": "client_email", "value": "gone@example.com"},
            headers=admin_headers,
        )
        entry_id = created.json()["id"]
        before = _sample("admin_blacklist_ops_total", {"op": "delete"})

        response = await client.delete(f"/api/blacklist/{entry_id}", headers=admin_headers)

        assert response.status_code == 204
        assert _sample("admin_blacklist_ops_total", {"op": "delete"}) == before + 1
