from functools import lru_cache

from pydantic import AnyHttpUrl, Field, PostgresDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_SECRET_MIN_LENGTH = 16
_PLACEHOLDER_SECRETS = frozenset(
    {
        "change_me_in_production",
        "changeme",
        "secret",
        "password",
        "token",
        "dev-token",
        "test",
        "123",
        "1234",
        "12345678",
    },
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    debug: bool = False
    log_level: str = "INFO"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid_levels:
            raise ValueError(
                f"Invalid log_level: {v!r}. Must be one of {sorted(valid_levels)}",
            )
        return upper

    postgres_dsn: PostgresDsn = Field(strict=True)

    cors_origins: list[str] = Field(default=["http://localhost:5173"])

    jwt_secret_key: str = Field(...)
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24 hours

    users_service_url: AnyHttpUrl = Field(strict=True)
    users_service_api_token: str = Field(strict=True)
    users_cache_ttl_seconds: int = 300
    cache_invalidation_token: str = Field(strict=True)

    event_receiver_url: AnyHttpUrl = Field(strict=True)
    event_receiver_api_key: str = Field(strict=True)
    event_publish_attempts: int = Field(default=3, ge=1, le=10)
    event_publish_timeout_seconds: float = Field(default=10.0, gt=0)

    login_max_failures: int = Field(default=5, ge=1)
    login_lockout_seconds: int = Field(default=300, ge=1)

    @model_validator(mode="after")
    def validate_secret_strength(self) -> Settings:
        """Refuse to start with weak or placeholder secrets outside DEBUG.

        DEBUG no longer affects authentication in any way (the auth bypass
        was removed); it only relaxes this check and switches log rendering.
        """
        if self.debug:
            return self
        secrets = {
            "JWT_SECRET_KEY": self.jwt_secret_key,
            "USERS_SERVICE_API_TOKEN": self.users_service_api_token,
            "CACHE_INVALIDATION_TOKEN": self.cache_invalidation_token,
            "EVENT_RECEIVER_API_KEY": self.event_receiver_api_key,
        }
        for name, value in secrets.items():
            if len(value) < _SECRET_MIN_LENGTH:
                raise ValueError(f"{name} must be at least {_SECRET_MIN_LENGTH} characters (got {len(value)})")
            if value.lower() in _PLACEHOLDER_SECRETS:
                raise ValueError(f"{name} is a placeholder value; set a real secret")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Single construction path for Settings (DI, middleware, and token minting share it)."""
    return Settings()
