"""
test_shared_db_full_coverage.py

Comprehensive unit tests for shared/db.py:
- database_url configuration
- _configure statement timeout
- get_pool creation, double-checked locking, and missing DSN error handling
- close_pool and reset_pool lifecycle
- connect() context manager with row_factory setup and restoration
"""

from unittest.mock import MagicMock
import pytest
from psycopg.rows import dict_row

from shared import db


def test_db_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/testdb")
    assert db.database_url() == "postgresql://user:pass@localhost:5432/testdb"

    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db.database_url() == ""


def test_db_configure():
    mock_conn = MagicMock()
    db._configure(mock_conn)
    mock_conn.execute.assert_called_once()
    assert "statement_timeout" in mock_conn.execute.call_args[0][0]
    mock_conn.commit.assert_called_once()


def test_db_pool_lifecycle(monkeypatch):
    # 1. Missing DATABASE_URL -> RuntimeError
    db.close_pool()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError) as exc:
        db.get_pool()
    assert "DATABASE_URL is not set" in str(exc.value)

    # 2. Valid DATABASE_URL with mocked ConnectionPool
    monkeypatch.setenv("DATABASE_URL", "postgresql://mock:mock@localhost:5432/mockdb")
    mock_pool_instance = MagicMock()
    mock_pool_cls = MagicMock(return_value=mock_pool_instance)
    mock_pool_cls.check_connection = MagicMock()
    monkeypatch.setattr(db, "ConnectionPool", mock_pool_cls)

    pool1 = db.get_pool()
    assert pool1 is mock_pool_instance

    # Idempotent call
    pool2 = db.get_pool()
    assert pool2 is mock_pool_instance
    assert mock_pool_cls.call_count == 1

    # 3. reset_pool & close_pool
    db.reset_pool()
    mock_pool_instance.close.assert_called_once()
    assert db._pool is None


def test_db_connect_context_manager(monkeypatch):
    mock_conn = MagicMock()
    mock_conn.row_factory = "default_factory"

    class MockPoolContext:
        def __enter__(self):
            return mock_conn
        def __exit__(self, *args):
            pass

    mock_pool = MagicMock()
    mock_pool.connection.return_value = MockPoolContext()
    monkeypatch.setattr(db, "get_pool", lambda: mock_pool)

    # 1. Standard checkout without changing row_factory
    with db.connect() as conn:
        assert conn is mock_conn
        assert conn.row_factory == "default_factory"
    assert mock_conn.row_factory == "default_factory"

    # 2. Checkout with dict_row factory - ensures it is restored afterwards
    with db.connect(row_factory=dict_row) as conn:
        assert conn is mock_conn
        assert conn.row_factory == dict_row

    # Restored to original
    assert mock_conn.row_factory == "default_factory"


def test_db_pool_double_checked_lock(monkeypatch):
    db.close_pool()
    monkeypatch.setenv("DATABASE_URL", "postgresql://mock:mock@localhost:5432/mockdb")
    existing = MagicMock()

    class FakeLock:
        def __enter__(self):
            db._pool = existing
            return self

        def __exit__(self, *a):
            pass

    monkeypatch.setattr(db, "_pool_lock", FakeLock())
    db._pool = None
    assert db.get_pool() is existing
