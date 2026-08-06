"""Shared fake DB connection used by mocked unit tests."""

from __future__ import annotations


class FakeDbCursor:
    def __init__(self, fetch_val=None, fetchall_val=None, rowcount=1):
        self._fetch_val = fetch_val
        self._fetchall_val = fetchall_val or []
        self.rowcount = rowcount
        self.executemany_calls = []

    def fetchone(self):
        return self._fetch_val

    def fetchall(self):
        return self._fetchall_val

    def executemany(self, sql, params_seq):
        self.executemany_calls.append((sql, params_seq))


class FakeDbConn:
    """In-memory stand-in for psycopg connections in unit tests."""

    def __init__(self):
        self.executed = []
        self._cursor_queue = []

    def queue_result(self, fetchone=None, fetchall=None, rowcount=1):
        self._cursor_queue.append(FakeDbCursor(fetchone, fetchall, rowcount))

    def cursor(self):
        return self

    def executemany(self, sql, params_seq):
        self.executed.append((sql, params_seq))

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if self._cursor_queue:
            return self._cursor_queue.pop(0)
        return FakeDbCursor()

    def commit(self):
        pass

    def rollback(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
