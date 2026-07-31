"""
shared/db.py - the single place that knows how to reach the database.

Why this exists
---------------
Before this module, seven call sites opened their own connection:

  shared/storage.py            configured (WAL, busy_timeout), via its own _connect
  domains/tax_expert/          configured, but through a *second* DB_PATH constant
    tax_sessions.py            naming the same file - a Path where storage's was a str
  shared/routers/auth.py       bare sqlite3.connect - no pragmas
  shared/routers/accounts.py   bare sqlite3.connect - no pragmas
  shared/routers/market.py     bare sqlite3.connect - no pragmas
  shared/config.py             bare sqlite3.connect - no pragmas
  domains/mutual_funds/        bare sqlite3.connect - no pragmas
    sessions.py

The five unconfigured ones get no `busy_timeout`, so a concurrent CAS upload -
which holds a write transaction for most of a second - makes them fail outright
with "database is locked" rather than waiting. They also use
`with sqlite3.connect(...)`, which commits but does *not* close, so the connection
survives until garbage collection and holds its locks that whole time.

Two constants naming one file also meant a test that redirected storage.DB_PATH to a
temp database left the tax store writing to the developer's real one.

Portability
-----------
This is also the seam for the Postgres migration. Everything that differs between
the two engines is meant to live here rather than in the modules that persist
things:

  - connection acquisition (a per-call connect today, a pool under Postgres)
  - parameter placeholders: `?` for sqlite3, `%s` for psycopg
  - engine setup (PRAGMAs have no Postgres equivalent)

Callers write `?` and go through `sql()`. Keep to SQL that both engines accept -
`INSERT ... ON CONFLICT (col) DO UPDATE` is understood by both, where
`INSERT OR REPLACE` is SQLite-only and additionally deletes-then-inserts, which
would drop columns the statement does not name.

DDL is deliberately NOT abstracted here. Type names diverge too far to paper over
(TEXT/REAL/INTEGER/BLOB against text/double precision/bigint/bytea), and schema
management moves to Alembic with the Postgres migration rather than to a
hand-rolled translation layer.
"""

import os
import sqlite3
import logging
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger(__name__)

# ── Location ──────────────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "metadata.sqlite3")

os.makedirs(DATA_DIR, exist_ok=True)

# The engine in use. Reading this to branch is a smell - prefer adding a helper here
# - but it lets a caller assert which engine it is talking to.
DIALECT = "sqlite"


def sql(statement: str) -> str:
    """
    Adapt a statement written with `?` placeholders to the active driver.

    A no-op on SQLite. Under psycopg this becomes a `?` -> `%s` rewrite, so callers
    can keep writing one style. Deliberately a function rather than a format string
    so the substitution has exactly one implementation.
    """
    return statement


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    """
    Configure a connection for a concurrent web server.

    Under the default rollback journal a writer takes an EXCLUSIVE lock over the whole
    database, so a 20k-row CAS upload (~0.7 s, plus fsyncs) blocked every reader - and
    past the busy timeout those requests failed with "database is locked" as a 500.
    WAL lets readers proceed during a write, which is the single most important setting
    here.

    - journal_mode=WAL is persistent (stored in the file header), so setting it on any
      connection is enough; it is applied per-connection anyway because a fresh
      database needs it once and this is the cheapest place to guarantee it.
    - synchronous=NORMAL rather than FULL: FULL fsyncs on every commit, and on a
      deployment whose disk is wiped on restart that durability buys nothing.
    - busy_timeout gives a blocked writer time to wait rather than failing instantly.

    WAL needs shared-memory mmap on the database's filesystem. That is fine on a
    container's local disk but can fail on some network mounts, so a failure here is
    logged and tolerated rather than fatal.
    """
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=15000")
    except sqlite3.DatabaseError as e:
        logger.warning("[DB] could not apply pragmas (WAL unsupported here?): %s", e)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """
    A configured connection that is always closed.

    `with sqlite3.connect(...)` commits but does NOT close - it is a transaction
    context, not a resource context. On an exception path the traceback keeps the
    frame (and therefore the connection) alive for an indeterminate time, holding
    locks. This wrapper commits on success, rolls back on failure, and closes either
    way.

    DB_PATH is read at call time, not captured at import, so redirecting it (as the
    tests do) affects every subsequent connection.
    """
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    _apply_pragmas(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
