from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRAM_", env_file=".env", extra="ignore")

    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://tram:tram-local-only@localhost:15433/tram"
    )
    viewer_token: SecretStr = SecretStr("")
    operator_token: SecretStr = SecretStr("")
    cursor_secret: SecretStr = SecretStr("")
    weatherapi_key: SecretStr = SecretStr("")
    timepad_token: SecretStr = SecretStr("")
    openapi_path: Path = Path("openapi.yaml")
    frontend_dist: Path = Path("frontend/dist")
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:8081"]
    )
    lease_seconds: int = Field(default=120, ge=30, le=3600)
    max_attempts: int = Field(default=3, ge=1, le=10)
    poll_seconds: float = Field(default=2, ge=0.1, le=60)

    @model_validator(mode="after")
    def supported_database(self):
        if not self.database_url.get_secret_value().startswith(
            ("postgresql+psycopg://", "postgresql+psycopg2://", "sqlite+pysqlite://")
        ):
            raise ValueError("Use PostgreSQL; SQLite is supported for local tests only")
        return self

    def require_api_secrets(self):
        values = [
            self.viewer_token.get_secret_value(),
            self.operator_token.get_secret_value(),
            self.cursor_secret.get_secret_value(),
        ]
        if any(len(value) < 32 for value in values) or len(set(values)) != 3:
            raise ValueError(
                "Set three different TRAM_VIEWER_TOKEN, TRAM_OPERATOR_TOKEN and TRAM_CURSOR_SECRET values of at least 32 characters"
            )
