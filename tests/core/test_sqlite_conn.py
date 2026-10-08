"""The two lock timeouts SQLite is given have to be the same one.

``sqlite3.connect(timeout=...)`` bounds how long the driver waits for a lock
before raising ``OperationalError``; ``PRAGMA busy_timeout`` bounds the same wait
inside the engine. The pragma was pinned to 10000 ms while the parameter stayed
free, so they agreed only at the default: a caller asking for 2s was told 10s by
the engine, and the request that was supposed to fail fast waited.
"""

import sqlite3

import pytest

from academic_hunter.core.infra.sqlite_conn import connect, connection


def test_the_busy_timeout_follows_the_timeout_it_was_given(tmp_path):
    conn = connect(str(tmp_path / "cache.db"), timeout=2.0)
    try:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 2000
    finally:
        conn.close()


def test_the_default_timeout_reaches_the_engine_too(tmp_path):
    conn = connect(str(tmp_path / "cache.db"))
    try:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 10000
    finally:
        conn.close()


def test_the_connection_is_closed_when_the_block_ends(tmp_path):
    """`with sqlite3.connect(...)` manages a transaction, not the handle."""
    db = str(tmp_path / "cache.db")
    with connection(db) as conn:
        conn.execute("CREATE TABLE t (x INTEGER)")

    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")
