"""Tests for application settings and database configuration validation."""

import pytest
from pydantic import ValidationError
from app.core.config import Settings


def test_config_loads_defaults():
    """Verify settings load properly with required PostgreSQL parameters."""
    cfg = Settings(
        POSTGRES_SERVER="db.example.com",
        POSTGRES_PORT=5432,
        POSTGRES_USER="testuser",
        POSTGRES_PASSWORD="secretpassword",
        POSTGRES_DB="testdb",
    )
    assert cfg.POSTGRES_SERVER == "db.example.com"
    assert cfg.POSTGRES_USER == "testuser"
    assert cfg.POSTGRES_DB == "testdb"
    assert "postgresql+psycopg2://testuser:secretpassword@db.example.com:5432/testdb" == cfg.sqlalchemy_database_uri


def test_sqlite_url_is_strictly_forbidden():
    """Verify that SQLite URLs are explicitly rejected to prevent silent in-memory fallback."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            DATABASE_URL="sqlite:///./test.db",
            POSTGRES_USER="postgres",
            POSTGRES_DB="support_ticket_db",
        )
    assert "SQLite and in-memory databases are strictly forbidden" in str(exc_info.value)


def test_memory_url_is_strictly_forbidden():
    """Verify that in-memory database URLs are explicitly rejected."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            DATABASE_URL="sqlite:///:memory:",
            POSTGRES_USER="postgres",
            POSTGRES_DB="support_ticket_db",
        )
    assert "SQLite and in-memory databases are strictly forbidden" in str(exc_info.value)


def test_missing_database_configuration_raises_error():
    """Verify that omitting both DATABASE_URL and POSTGRES_USER/DB raises ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            SECRET_KEY="a-sufficiently-long-test-secret-key-1234567890",
            POSTGRES_USER=None,
            POSTGRES_DB=None,
            DATABASE_URL=None,
        )
    assert "Database configuration incomplete" in str(exc_info.value)


def test_missing_secret_key_fails_validation():
    """Verify that omitting SECRET_KEY when no .env is available raises ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            SECRET_KEY=None,
            POSTGRES_USER="testuser",
            POSTGRES_DB="testdb",
        )
    assert "SECRET_KEY is missing" in str(exc_info.value)


def test_short_secret_key_fails_validation():
    """Verify that SECRET_KEY shorter than 32 characters is rejected."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            SECRET_KEY="short-secret-key-less-than-32",
            POSTGRES_USER="testuser",
            POSTGRES_DB="testdb",
        )
    assert "SECRET_KEY is too short" in str(exc_info.value)


def test_insecure_default_secret_key_fails_validation():
    """Verify that known placeholder default keys are strictly rejected."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            SECRET_KEY="change-this-to-a-secure-random-secret-key-in-production",
            POSTGRES_USER="testuser",
            POSTGRES_DB="testdb",
        )
    assert "Insecure or default placeholder SECRET_KEY detected" in str(exc_info.value)


def test_valid_strong_secret_key_passes_validation():
    """Verify that a valid, strong SECRET_KEY passes validation."""
    cfg = Settings(
        _env_file=None,
        SECRET_KEY="my-super-secret-unique-production-key-value-at-least-32-chars",
        POSTGRES_USER="testuser",
        POSTGRES_DB="testdb",
    )
    assert cfg.SECRET_KEY == "my-super-secret-unique-production-key-value-at-least-32-chars"


def test_direct_database_url_precedence():
    """Verify direct DATABASE_URL overrides individual POSTGRES_* settings."""
    direct_url = "postgresql+psycopg2://custom_user:custom_pass@custom_host:5433/custom_db"
    cfg = Settings(
        DATABASE_URL=direct_url,
        POSTGRES_SERVER="ignored_host",
        POSTGRES_USER="ignored_user",
        POSTGRES_DB="ignored_db",
    )
    assert cfg.sqlalchemy_database_uri == direct_url
