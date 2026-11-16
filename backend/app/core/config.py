"""Application Configuration using Pydantic Settings."""

from typing import Any, List, Literal, Union

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore"
    )

    # Core App
    APP_ENV: Literal["development", "staging", "production", "test"] = "development"
    APP_NAME: str = "Enterprise Sales Agent Platform"
    APP_SECRET_KEY: str = Field(
        default="dev-secret-key-super-secure-32-chars-long-string!",
        min_length=32,
        description="Cryptographic secret key for signing tokens",
    )
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DEBUG: bool = True

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on", "t")
        return False

    # Database
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./platform.db",
        description="Async SQLAlchemy database URL (PostgreSQL in production)",
    )
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_TIMEOUT: int = 30
    DB_ECHO: bool = False

    # Redis & Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    CELERY_TASK_DEFAULT_QUEUE: str = "default"

    # Authentication & Security
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    COOKIE_DOMAIN: Union[str, None] = None
    CSRF_SECRET_KEY: str = "dev-csrf-secret-key-32-chars-long-string!"

    # CORS
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]
    FRONTEND_URL: str = "http://localhost:5173"
    BACKEND_URL: str = "http://localhost:8000"

    # Logging & Observability
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["json", "text"] = "json"
    SENTRY_DSN: Union[str, None] = None
    OTEL_EXPORTER_OTLP_ENDPOINT: Union[str, None] = None

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = False
    RATE_LIMIT_DEFAULT: str = "100/minute"
    RATE_LIMIT_AUTH: str = "10/minute"
    RATE_LIMIT_EXPENSIVE_AGENT: str = "15/minute"

    # AI Provider Gateway
    AI_PROVIDER: str = "mock"
    OPENAI_API_KEY: str = "mock-openai-key"
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_FALLBACK_MODEL: str = "gpt-4o-mini"
    AI_TIMEOUT_SECONDS: int = 30
    AI_MAX_RETRIES: int = 2

    # Integrations
    APOLLO_API_KEY: str = "mock-apollo-key"
    APOLLO_BASE_URL: str = "https://api.apollo.io/v1"

    HUBSPOT_ACCESS_TOKEN: str = "mock-hubspot-token"
    HUBSPOT_BASE_URL: str = "https://api.hubapi.com"
    GHL_ACCESS_TOKEN: str = "mock-ghl-token"
    GHL_LOCATION_ID: str = "mock-location-id"
    GHL_BASE_URL: str = "https://services.leadconnectorhq.com"

    SMS_PROVIDER: str = "mock"
    SMS_PROVIDER_API_KEY: str = "mock-sms-key"
    SMS_PROVIDER_PHONE_NUMBER: str = "+15551234567"
    SMS_WEBHOOK_SECRET: str = "mock-webhook-secret"

    MICROSOFT_CLIENT_ID: str = "mock-ms-id"
    MICROSOFT_CLIENT_SECRET: str = "mock-ms-secret"
    MICROSOFT_TENANT_ID: str = "mock-ms-tenant"

    OBJECT_STORAGE_PROVIDER: str = "mock"
    OBJECT_STORAGE_ENDPOINT: str = "http://localhost:9000"
    OBJECT_STORAGE_ACCESS_KEY: str = "mock-access"
    OBJECT_STORAGE_SECRET_KEY: str = "mock-secret"
    OBJECT_STORAGE_BUCKET: str = "sales-agent-artifacts"
    OBJECT_STORAGE_REGION: str = "us-east-1"
    OBJECT_STORAGE_USE_SSL: bool = False

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                import json

                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    def validate_production(self) -> None:
        """Validate critical configuration constraints for production environments."""
        if self.APP_ENV == "production":
            if "dev-secret" in self.APP_SECRET_KEY or len(self.APP_SECRET_KEY) < 32:
                raise ValueError(
                    "APP_SECRET_KEY must be a secure production secret of >= 32 characters."
                )
            if not self.COOKIE_SECURE:
                raise ValueError("COOKIE_SECURE must be true in production.")
            if not self.DATABASE_URL.startswith("postgresql"):
                raise ValueError("Production requires PostgreSQL database with asyncpg.")


settings = Settings()
