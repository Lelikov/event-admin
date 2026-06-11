"""App factory smoke tests."""

from event_admin.main import create_app
from tests.conftest import FakeProvider


async def test_health_is_public(client) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_factory_uses_provided_settings(settings, fakes) -> None:
    app = create_app(settings, provider=FakeProvider(settings, fakes))
    assert app.title == "event-admin"
