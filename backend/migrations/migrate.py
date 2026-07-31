"""
Apply pending SQL migrations.

    python -m migrations.migrate          # apply everything pending
    python -m migrations.migrate --status # show what would run, change nothing

Why not Alembic
---------------
Alembic requires SQLAlchemy, which is ~30 MB RSS on a 512 MB instance for a
codebase with no ORM. Its main draw is autogenerate, which diffs declarative models
- and with no models there is nothing to diff, so every migration would be an
`op.execute()` wrapper around the same raw SQL that lives in these files. This is
that, minus the dependency.

Guarantees
----------
- Each file runs at most once, recorded in `schema_migrations`.
- A file runs inside a transaction with its ledger row, so a failure applies
  nothing and leaves nothing marked. Postgres has transactional DDL, which is what
  makes that possible; the SQLite version of this could not have offered it.
- A lock is taken first, so two instances booting at once cannot both apply the
  same migration.
- Applied files are checksummed. Editing a migration that has already run is a
  silent way to make environments diverge, so it is reported as an error rather
  than ignored.
"""

import argparse
import hashlib
import logging
import pathlib
import sys

# Importable both as `python -m migrations.migrate` from backend/ and directly.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from shared import db  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("migrate")

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent

# Any positive int; two instances calling this agree on it because it is a constant.
_LOCK_KEY = 8474219903


def _discover():
    """Every .sql file, ordered by its numeric prefix."""
    files = sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name)
    return [(p.name, p.read_text(encoding="utf-8")) for p in files]


def _checksum(body: str) -> str:
    # Newlines are normalised so a checkout with CRLF does not report every applied
    # migration as modified.
    return hashlib.sha256(body.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def _ensure_ledger(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name        text PRIMARY KEY,
            checksum    text NOT NULL,
            applied_at  timestamptz NOT NULL DEFAULT now()
        )
    """)


def _applied(conn) -> dict:
    rows = conn.execute("SELECT name, checksum FROM schema_migrations").fetchall()
    return {name: checksum for name, checksum in rows}


def status() -> int:
    with db.connect() as conn:
        _ensure_ledger(conn)
        applied = _applied(conn)

    drifted, pending, done = [], [], []
    for name, body in _discover():
        if name not in applied:
            pending.append(name)
        elif applied[name] != _checksum(body):
            drifted.append(name)
        else:
            done.append(name)

    for name in done:
        logger.info("  applied  %s", name)
    for name in pending:
        logger.info("  PENDING  %s", name)
    for name in drifted:
        logger.error("  CHANGED  %s  (already applied, but the file has been edited)", name)

    if drifted:
        logger.error(
            "\n%d applied migration(s) have been modified. Editing an applied "
            "migration makes environments diverge silently - add a new file instead.",
            len(drifted),
        )
        return 1
    logger.info("\n%d applied, %d pending", len(done), len(pending))
    return 0


def upgrade() -> int:
    migrations = _discover()
    if not migrations:
        logger.info("no migration files found")
        return 0

    with db.connect() as conn:
        # Serialises concurrent booters. Session-scoped rather than transactional
        # because the ledger check and each apply are separate transactions; it is
        # released explicitly below.
        conn.execute("SELECT pg_advisory_lock(%s)", (_LOCK_KEY,))
        try:
            _ensure_ledger(conn)
            applied = _applied(conn)

            drifted = [
                name for name, body in migrations
                if name in applied and applied[name] != _checksum(body)
            ]
            if drifted:
                logger.error(
                    "refusing to run: these applied migrations have been edited: %s",
                    ", ".join(drifted),
                )
                return 1

            pending = [(n, b) for n, b in migrations if n not in applied]
            if not pending:
                logger.info("nothing to do - %d migration(s) already applied", len(applied))
                return 0

            for name, body in pending:
                logger.info("applying %s ...", name)
                # One transaction per migration, covering both the DDL and its
                # ledger row, so a failure leaves neither behind.
                with conn.transaction():
                    conn.execute(body)
                    conn.execute(
                        "INSERT INTO schema_migrations (name, checksum) VALUES (%s, %s)",
                        (name, _checksum(body)),
                    )
                logger.info("           ok")

            logger.info("applied %d migration(s)", len(pending))
            return 0
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (_LOCK_KEY,))


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply pending SQL migrations.")
    parser.add_argument(
        "--status", action="store_true", help="report state without changing anything"
    )
    args = parser.parse_args()

    if not db.database_url():
        logger.error("DATABASE_URL is not set - see ONBOARDING.md")
        return 2
    try:
        return status() if args.status else upgrade()
    finally:
        db.close_pool()


if __name__ == "__main__":
    raise SystemExit(main())
