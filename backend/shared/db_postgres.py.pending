"""
shared/db.py - the only module that reaches the database.

Engine
------
PostgreSQL via psycopg 3. SQLite is gone: the deployment now keeps user data
across restarts, and a file-backed database on an ephemeral container cannot.

No ORM. The codebase has never had one, every query here is hand-written SQL, and
SQLAlchemy would cost roughly 30 MB RSS on a 512 MB box for machinery nothing uses.
That also decided migrations - Alembic requires SQLAlchemy, and without ORM models
its autogenerate has nothing to diff, so its migrations would be `op.execute()`
wrappers around the same raw SQL. `migrations/` holds numbered .sql files and
`migrate.py` applies them against a `schema_migrations` ledger.

Pooling
-------
Connecting per request is not viable against a network database: a TLS handshake
plus authentication is 50-100 ms, where the SQLite open it replaced was ~10 us. The
pool is sized against the anyio threadpool cap (FINANCEBUDDY_SYNC_CONCURRENCY,
default 8) - that cap is the real ceiling on concurrent sync handlers, so more
connections than that can only sit idle while still counting against the server's
connection limit, which is small on a free tier.

min_size is 1 rather than max_size: this instance idles most of the time and
spins down, so holding open connections buys nothing and a pooler charges for
them.

Transaction-mode poolers
------------------------
Supabase's Supavisor on port 6543, and pgBouncer generally, multiplex one server
connection across many clients per *transaction*. Server-side prepared statements
do not survive that, so prepare_threshold is disabled - otherwise psycopg prepares
a statement on one backend and later executes it on another, which fails with
"prepared statement does not exist" only under concurrency, i.e. in production and
not in a test.

The same constraint rules out anything session-scoped: no LISTEN/NOTIFY, no
server-side cursors, no SET without LOCAL, no advisory locks held across
statements.

Portability
-----------
This talks to Postgres, not to a vendor. Everything provider-specific is a
connection string, so Supabase, Neon, RDS, Railway or a local server are the same
code. Nothing here imports a vendor SDK, and no schema object references a
provider-managed table.
"""

import os
import logging
import threading
from contextlib import contextmanager
from typing import Iterator, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

try:  # loading a .env is a developer convenience; the platform sets real env vars
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - python-dotenv absent in a slim image
    pass

logger = logging.getLogger(__name__)


def database_url() -> str:
    """
    The DSN, read at call time so a test can redirect it.

    Deliberately not cached: the test suite points this at a throwaway database by
    setting the environment variable, and a module-level constant captured at import
    would ignore that.
    """
    return os.getenv("DATABASE_URL", "")


# Bounded by the anyio threadpool cap rather than guessed - see the module docstring.
POOL_MIN_SIZE = int(os.getenv("FINANCEBUDDY_DB_POOL_MIN", "1"))
POOL_MAX_SIZE = int(os.getenv("FINANCEBUDDY_DB_POOL_MAX", "6"))

# A query that has run this long is not going to help the request that started it,
# and on a shared-CPU instance it is actively taking time from other requests.
STATEMENT_TIMEOUT_MS = int(os.getenv("FINANCEBUDDY_DB_STATEMENT_TIMEOUT_MS", "15000"))

_pool: Optional[ConnectionPool] = None
_pool_lock = threading.Lock()


def _configure(conn: psycopg.Connection) -> None:
    """Applied once per physical connection, not per checkout."""
    conn.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")


def get_pool() -> ConnectionPool:
    """
    The process-wide pool, created on first use.

    Built lazily rather than at import: importing this module must not require a
    reachable database, or the test suite and any offline tooling cannot even load
    the app. Double-checked under a lock so two concurrent first requests do not
    each build one - the same check-then-act that the tax session store got wrong.
    """
    global _pool
    if _pool is not None:
        return _pool

    with _pool_lock:
        if _pool is not None:
            return _pool

        dsn = database_url()
        if not dsn:
            raise RuntimeError(
                "DATABASE_URL is not set. Postgres is required - see DEPLOYMENT.md."
            )

        _pool = ConnectionPool(
            conninfo=dsn,
            min_size=POOL_MIN_SIZE,
            max_size=POOL_MAX_SIZE,
            timeout=10.0,          # wait for a free connection before failing
            max_lifetime=1800.0,   # recycle, so a pooler-side restart cannot pin a dead socket
            max_idle=300.0,
            configure=_configure,
            kwargs={
                # See "Transaction-mode poolers" above. Not optional against Supavisor.
                "prepare_threshold": None,
                "application_name": "financebuddy",
            },
            open=True,
            check=ConnectionPool.check_connection,
        )
        logger.info(
            "[DB] pool ready (min=%d max=%d)", POOL_MIN_SIZE, POOL_MAX_SIZE
        )
        return _pool


def close_pool() -> None:
    """Shut the pool down. Called from the app's lifespan handler and by tests."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None


def reset_pool() -> None:
    """
    Drop the pool so the next call rebuilds it against the current DATABASE_URL.

    Exists for the test suite, which points the DSN at a throwaway database after
    this module has already been imported.
    """
    close_pool()


@contextmanager
def connect(row_factory=None) -> Iterator[psycopg.Connection]:
    """
    A pooled connection wrapped in one transaction.

    Commits on success, rolls back on any exception, and always returns the
    connection to the pool. Callers do not commit; doing so mid-block would end the
    transaction early and leave the rest of the block running outside it.

    Pass row_factory=dict_row where a query wants column access by name; the default
    tuple factory is the cheapest and is what most callers here want.
    """
    pool = get_pool()
    with pool.connection() as conn:
        if row_factory is not None:
            conn.row_factory = row_factory
        # psycopg's connection context manager already commits on clean exit and
        # rolls back on exception, so no explicit handling is needed here.
        yield conn


__all__ = [
    "connect",
    "get_pool",
    "close_pool",
    "reset_pool",
    "database_url",
    "dict_row",
]
