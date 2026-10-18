from sqlalchemy import text, inspect
from sqlalchemy.orm import Session
from alembic.config import Config
from alembic import command

from app.database.session import check_database_connection, engine
from app.database.base import Base
from app.core.config import settings
from tests.conftest import test_engine


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


def test_alembic_migrations_lifecycle_on_clean_database():
    """Verify Alembic migration upgrade to head and downgrade to base on clean test database."""
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.sqlalchemy_test_database_uri)

    # 1. Clean slate: drop all existing tables and alembic_version tracking table
    Base.metadata.drop_all(bind=test_engine)
    with test_engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version CASCADE;"))
        conn.commit()

    # 2. Run migrations to head
    command.upgrade(alembic_cfg, "head")

    # 3. Verify all expected tables exist
    inspector = inspect(test_engine)
    tables = inspector.get_table_names()
    assert "users" in tables
    assert "tickets" in tables
    assert "comments" in tables
    assert "ticket_history" in tables
    assert "alembic_version" in tables

    # 4. Downgrade back to base
    command.downgrade(alembic_cfg, "base")

    # 5. Verify all tables are removed
    inspector_after = inspect(test_engine)
    tables_after = inspector_after.get_table_names()
    assert "tickets" not in tables_after
    assert "comments" not in tables_after
    assert "ticket_history" not in tables_after
    assert "users" not in tables_after

    # 6. Re-upgrade to head so database remains in clean ready state for other tests
    command.upgrade(alembic_cfg, "head")
