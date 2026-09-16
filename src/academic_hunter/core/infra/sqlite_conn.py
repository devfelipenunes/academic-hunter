"""Shared SQLite connection setup.

Both the request cache and the MCP config-history store open short-lived
connections from several threads. SQLite's defaults are hostile to that: the
rollback journal makes any writer block every reader, and with no busy timeout
a concurrent writer fails immediately with ``database is locked`` instead of
waiting for the lock to clear.

WAL mode is what makes the read-while-writing pattern work, and it is a
connection-level setting, so every ``connect()`` site has to apply it — hence
this helper rather than open-coding the pragmas in each module.
"""

import sqlite3
from contextlib import contextmanager


@contextmanager
def connection(db_path: str, timeout: float = 10.0):
    """A connection that is closed when the block ends, around a transaction.

    ``with sqlite3.connect(...) as conn`` reads like it closes the database and
    does not: that statement manages a *transaction*, and the handle lives on
    until the garbage collector finalises it. Measured — after such a block the
    ``-wal`` file is still on disk, and it disappears only at the collection
    that finalises the connection.

    Two consequences, both real. A cache that has served a thousand requests is
    still holding every handle it ever opened. And the ``-wal`` vanishes at a
    moment nothing controls, which is what made ``shutil.rmtree`` fail on a
    temporary directory: the file was listed, and gone by the time it was
    unlinked.

    Use this rather than bare ``connect()`` whenever the caller reads like it is
    done with the database at the end of the block.
    """
    conn = connect(db_path, timeout)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def connect(db_path: str, timeout: float = 10.0) -> sqlite3.Connection:
    """Open a SQLite connection configured for concurrent access.

    Args:
        db_path: Path to the database file.
        timeout: Seconds the driver waits for a lock before raising
            ``OperationalError``. The ``busy_timeout`` pragma below sets the
            same bound at the engine level, so both agree.

    Returns:
        A connection with WAL journalling and a busy timeout applied.
    """
    conn = sqlite3.connect(db_path, timeout=timeout)
    # Readers do not block the writer and vice versa.
    conn.execute("PRAGMA journal_mode=WAL")
    # Safe with WAL: a crash cannot corrupt the database, and this avoids an
    # fsync per transaction — acceptable for a cache and a config history.
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn
