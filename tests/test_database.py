"""Tests for database connectivity and session lifecycle against PostgreSQL."""

from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database.session import check_database_connection, engine


def test_database_live_connection():
    """Verify engine establishes live connection to PostgreSQL."""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar()
        assert result == 1


def test_check_database_connection_utility():
    """Verify check_database_connection returns True for healthy PostgreSQL connection."""
    assert check_database_connection() is True


def test_session_transaction_lifecycle(db_session: Session):
    """Verify basic session query execution in transaction."""
    val = db_session.execute(text("SELECT 42")).scalar()
    assert val == 42
