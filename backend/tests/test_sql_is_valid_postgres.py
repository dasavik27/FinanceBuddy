"""
Static validation of every SQL statement in the codebase.

This does not need a database, which is the point: it catches the class of mistake
that blind hand-written SQL is most prone to - a typo, an unbalanced paren, a clause
in the wrong order, SQLite syntax left behind after the Postgres port - at test time
rather than at runtime against a live connection.

It is not a substitute for executing the queries. A statement can parse perfectly and
still reference a column that does not exist. Treat a green run here as "the SQL is
well-formed Postgres", nothing more.
"""

import ast
import pathlib
import re

import pytest

sqlglot = pytest.importorskip("sqlglot", reason="sqlglot is a dev-only dependency")
from sqlglot.errors import ParseError  # noqa: E402

BACKEND = pathlib.Path(__file__).resolve().parent.parent

# Substrings that mean "this string is SQL". Deliberately narrow - a false positive
# here fails the suite on a sentence in a docstring.
# `UPDATE \w+ SET` rather than `UPDATE \w`: the looser form matched every docstring
# beginning "Update the ...", and three of them were reported as malformed SQL.
SQL_START = re.compile(
    r"^\s*(SELECT\s|INSERT\s+INTO\s|UPDATE\s+\w+\s+SET\s|DELETE\s+FROM\s"
    r"|CREATE\s+(TABLE|INDEX|UNIQUE)\s|ALTER\s+TABLE\s|WITH\s+\w+\s+AS\s)",
    re.IGNORECASE,
)

# psycopg placeholders are not valid SQL to a parser; swap in a literal that is.
PLACEHOLDER = re.compile(r"%s")

# Statements assembled from fragments across several string literals. Each fragment
# alone is not parseable, so they are checked as a whole where they are built.
KNOWN_FRAGMENTS = {
    "SELECT session_id, user_id, upload_type, created_at, updated_at,",
    "       total_value, total_invested, num_funds, is_partial,",
    "       statement_period, summary",
    "FROM sessions WHERE TRUE",
    "SELECT COUNT(*) FROM mf_portfolio_snapshots WHERE",
    "DELETE FROM mf_portfolio_snapshots WHERE",
}


def _sql_literals(path: pathlib.Path):
    """Every string constant in a module that looks like a SQL statement."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        text = node.value
        if text.strip() in KNOWN_FRAGMENTS:
            continue
        if SQL_START.match(text):
            yield node.lineno, text


def _python_sources():
    for path in BACKEND.rglob("*.py"):
        if any(part in path.parts for part in ("venv", ".venv", "venv_finance", "__pycache__", "tests", "node_modules", ".git")):
            continue
        yield path


def _iter_statements():
    for path in _python_sources():
        for lineno, text in _sql_literals(path):
            yield path, lineno, text


ALL_STATEMENTS = list(_iter_statements())


def test_the_scanner_actually_finds_statements():
    """A scanner that silently matches nothing would make every test below vacuous."""
    assert len(ALL_STATEMENTS) >= 15, (
        f"only found {len(ALL_STATEMENTS)} SQL literals - the detector is probably broken"
    )


@pytest.mark.parametrize(
    "path,lineno,statement",
    ALL_STATEMENTS,
    ids=[f"{p.relative_to(BACKEND)}:{n}" for p, n, _ in ALL_STATEMENTS],
)
def test_inline_sql_parses_as_postgres(path, lineno, statement):
    try:
        parsed = sqlglot.parse(PLACEHOLDER.sub("NULL", statement), dialect="postgres")
    except ParseError as e:
        pytest.fail(f"{path.relative_to(BACKEND)}:{lineno} is not valid Postgres:\n{e}")
    assert parsed and parsed[0] is not None


def test_migrations_parse_as_postgres():
    """The schema itself, which nothing else here would catch."""
    files = sorted((BACKEND / "migrations").glob("*.sql"))
    assert files, "no migration files found"

    for path in files:
        body = path.read_text(encoding="utf-8")
        try:
            statements = sqlglot.parse(body, dialect="postgres")
        except ParseError as e:
            pytest.fail(f"{path.name} is not valid Postgres:\n{e}")
        assert any(s is not None for s in statements), f"{path.name} parsed to nothing"


def test_no_sqlite_syntax_survives_the_port():
    """
    Constructs that are valid SQLite and either invalid or differently-behaved in
    Postgres. `INSERT OR REPLACE` is the dangerous one - Postgres rejects it outright,
    but its SQLite semantics are delete-then-insert, so a translation to plain INSERT
    would silently drop unnamed columns.
    """
    banned = {
        "INSERT OR REPLACE": "use INSERT ... ON CONFLICT DO UPDATE",
        "AUTOINCREMENT": "use a bigserial or identity column",
        "PRAGMA ": "no Postgres equivalent",
        "datetime('now'": "use now() or CURRENT_TIMESTAMP",
        "IFNULL(": "use COALESCE",
    }
    offenders = []
    for path in _python_sources():
        text = path.read_text(encoding="utf-8")
        for needle, advice in banned.items():
            if needle.lower() in text.lower():
                offenders.append(f"{path.relative_to(BACKEND)}: {needle!r} - {advice}")

    assert not offenders, "SQLite-only syntax left behind:\n" + "\n".join(offenders)


def test_no_qmark_placeholders_remain():
    """
    psycopg uses %s. A leftover `?` is not a syntax error to the server - it is a
    parameter that never binds, so the statement fails only when executed.
    """
    offenders = []
    for path, lineno, statement in ALL_STATEMENTS:
        # `?` is a real Postgres operator on jsonb ("does this key exist"), so only
        # flag it where it sits in a value position.
        if re.search(r"(VALUES\s*\([^)]*\?|=\s*\?|IN\s*\(\s*\?)", statement):
            offenders.append(f"{path.relative_to(BACKEND)}:{lineno}")
    assert not offenders, "sqlite3-style placeholders remain in:\n" + "\n".join(offenders)
