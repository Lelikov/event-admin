"""CORS posture: no credentialed CORS; 401s still carry CORS headers."""

ORIGIN = "http://localhost:5173"


async def test_preflight_succeeds_without_token(client) -> None:
    response = await client.options(
        "/bookings",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


async def test_cors_is_not_credentialed(client) -> None:
    response = await client.options(
        "/bookings",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-credentials" not in response.headers


async def test_401_response_carries_cors_headers(client) -> None:
    """CORS middleware is outermost: auth failures stay readable for the SPA."""
    response = await client.get("/bookings", headers={"Origin": ORIGIN})
    assert response.status_code == 401
    assert response.headers.get("access-control-allow-origin") == ORIGIN


async def test_disallowed_origin_gets_no_cors_headers(client) -> None:
    response = await client.options(
        "/bookings",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") != "http://evil.example.com"
