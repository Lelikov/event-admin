"""Settings validation: weak/placeholder secrets are refused outside DEBUG."""

import pytest
from pydantic import ValidationError

from tests.conftest import make_settings


def test_strong_secrets_accepted() -> None:
    settings = make_settings()
    assert settings.debug is False


def test_short_secret_rejected_outside_debug() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        make_settings(jwt_secret_key="short")


def test_placeholder_secret_rejected_outside_debug() -> None:
    with pytest.raises(ValidationError, match="placeholder"):
        make_settings(jwt_secret_key="CHANGE_ME_IN_PRODUCTION")


@pytest.mark.parametrize(
    "field",
    ["users_service_api_token", "cache_invalidation_token", "event_receiver_api_key"],
)
def test_all_secrets_are_validated(field) -> None:
    with pytest.raises(ValidationError):
        make_settings(**{field: "123"})


def test_debug_relaxes_secret_validation_only() -> None:
    settings = make_settings(debug=True, jwt_secret_key="dev")
    assert settings.jwt_secret_key == "dev"


def test_invalid_log_level_rejected() -> None:
    with pytest.raises(ValidationError, match="log_level"):
        make_settings(log_level="LOUD")
