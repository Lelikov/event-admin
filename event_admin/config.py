from pydantic import AnyHttpUrl, Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
