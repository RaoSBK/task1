"""Application settings and environment configuration."""

from typing import Optional
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Known insecure placeholder secrets that must never be used
INSECURE_SECRET_KEYS: tuple[str, ...] = (
    "dev-secret-key-support-ticket-system-evaluation-2026-min-32-bytes",
    "change-this-to-a-secure-random-secret-key-in-production",
    "your_secure_password_here",
    "your_secret_key_here",
    "secret",
    "changeme",
    "secret_key",
    "secret-key",
)


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # General Project Settings
    PROJECT_NAME: str = "Customer Support Ticket Management System"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"

    # PostgreSQL Database Settings
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: Optional[str] = None

    # Direct database connection URL (optional override)
    DATABASE_URL: Optional[str] = None

    # Test database configuration
    POSTGRES_TEST_DB: Optional[str] = None
    TEST_DATABASE_URL: Optional[str] = None

    # Security & JWT Settings
    SECRET_KEY: Optional[str] = None
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    INITIAL_ADMIN_EMAIL: Optional[str] = None
    INITIAL_ADMIN_PASSWORD: Optional[str] = None

    @field_validator("SECRET_KEY", mode="before")
    @classmethod
    def validate_secret_key(cls, v: Optional[str]) -> str:
        """Enforce presence, minimum length, and reject known insecure default JWT secrets."""
        if v is None or not str(v).strip():
            raise ValueError(
                "SECRET_KEY is missing. A secure cryptographic secret key must be set via "
                "environment configuration (.env) and cannot be empty."
            )
        cleaned = str(v).strip()
        if len(cleaned) < 32:
            raise ValueError(
                f"SECRET_KEY is too short ({len(cleaned)} characters). It must be at least 32 "
                "characters long to guarantee cryptographic security for HS256 JWT tokens."
            )
        if cleaned.lower() in [k.lower() for k in INSECURE_SECRET_KEYS]:
            raise ValueError(
                "Insecure or default placeholder SECRET_KEY detected. "
                "You must configure a strong, unique secret key for production and local environments."
            )
        return cleaned

    @field_validator("DATABASE_URL", "TEST_DATABASE_URL", mode="before")
    @classmethod
    def validate_not_in_memory_or_sqlite(cls, v: Optional[str]) -> Optional[str]:
        """Strictly disallow SQLite or in-memory fallback."""
        if v is not None and isinstance(v, str) and v.strip():
            cleaned = v.strip().lower()
            if "sqlite" in cleaned or ":memory:" in cleaned:
                raise ValueError(
                    "SQLite and in-memory databases are strictly forbidden. "
                    "A valid PostgreSQL connection must be configured."
                )
            return v.strip()
        return None

    @model_validator(mode="after")
    def validate_database_credentials(self) -> "Settings":
        """Verify that necessary PostgreSQL settings are provided."""
        if not self.DATABASE_URL:
            if not self.POSTGRES_USER or not self.POSTGRES_DB:
                raise ValueError(
                    "Database configuration incomplete: either DATABASE_URL or both "
                    "POSTGRES_USER and POSTGRES_DB must be configured via environment variables. "
                    "Silent fallback to in-memory databases is not allowed."
                )
        return self

    @property
    def sqlalchemy_database_uri(self) -> str:
        """Construct the primary PostgreSQL SQLAlchemy connection string."""
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+psycopg2://", 1)
            elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
                url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
            return url

        password_component = f":{self.POSTGRES_PASSWORD}" if self.POSTGRES_PASSWORD else ""
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}{password_component}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def sqlalchemy_test_database_uri(self) -> str:
        """Construct the test PostgreSQL SQLAlchemy connection string."""
        if self.TEST_DATABASE_URL:
            url = self.TEST_DATABASE_URL
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+psycopg2://", 1)
            elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
                url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
            return url

        test_db = (
            self.POSTGRES_TEST_DB
            or (f"{self.POSTGRES_DB}_test" if self.POSTGRES_DB else "support_ticket_test")
        )
        password_component = f":{self.POSTGRES_PASSWORD}" if self.POSTGRES_PASSWORD else ""
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}{password_component}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{test_db}"
        )


settings = Settings()
