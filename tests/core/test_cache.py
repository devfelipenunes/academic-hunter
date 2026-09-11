"""Tests for SQLiteCache — persistent request caching."""
import logging
import os
import sqlite3
import tempfile

import pytest

from academic_hunter.core.infra.cache import SQLiteCache
from academic_hunter.core.infra.sqlite_conn import connect


def _make_cache():
    """Create a SQLiteCache with a temp file."""
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    cache = SQLiteCache(db_path=f.name)
    return cache, f.name


def test_cache_set_and_get():
    """Setting and getting a value works correctly."""
    cache, path = _make_cache()
    try:
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
    finally:
        os.unlink(path)


def test_cache_get_missing():
    """Getting a missing key returns None."""
    cache, path = _make_cache()
    try:
        assert cache.get("nonexistent") is None
    finally:
        os.unlink(path)


def test_cache_overwrite():
    """Setting an existing key overwrites the value."""
    cache, path = _make_cache()
    try:
        cache.set("key", "old_value")
        cache.set("key", "new_value")
        assert cache.get("key") == "new_value"
    finally:
        os.unlink(path)


def test_cache_multiple_keys():
    """Multiple keys are stored and retrieved independently."""
    cache, path = _make_cache()
    try:
        cache.set("a", "1")
        cache.set("b", "2")
        assert cache.get("a") == "1"
        assert cache.get("b") == "2"
    finally:
        os.unlink(path)


def test_cache_empty_value():
    """Empty string values are stored correctly."""
    cache, path = _make_cache()
    try:
        cache.set("empty", "")
        assert cache.get("empty") == ""
    finally:
        os.unlink(path)


def _corrupt(path):
    """Break the database for real.

    Overwriting only the main file is not enough: SQLite keeps a `-wal` and a
    `-shm` beside it, and it recovers the database from them. The first version
    of this helper left them in place, so nothing raised, `get` returned None
    because the key genuinely was not there, and the test passed without ever
    reaching the error branch it was written for.
    """
    with open(path, "w") as f:
        f.write("not a valid sqlite file")
    for sidecar in (path + "-wal", path + "-shm"):
        if os.path.exists(sidecar):
            os.unlink(sidecar)


def test_cache_get_error_returns_none():
    """get returns None when database is corrupted."""
    cache, path = _make_cache()
    try:
        _corrupt(path)
        assert cache.get("key") is None
    finally:
        os.unlink(path)


def test_the_corruption_actually_reaches_the_error_branch():
    """The guard on the test above: it must fail for the reason it claims."""
    cache, path = _make_cache()
    try:
        _corrupt(path)
        with pytest.raises(sqlite3.DatabaseError):
            connect(path)
    finally:
        os.unlink(path)


def test_a_broken_cache_says_so(caplog):
    """A miss and a corrupt cache both return None, so the failure must be logged.

    Measured defect: `get` swallowed every exception in silence while `set`
    logged its own. A cache answering None to everything turns every run into a
    full network run, and the symptom is slowness — nothing points at the file.
    """
    cache, path = _make_cache()
    try:
        _corrupt(path)

        with caplog.at_level(logging.WARNING, logger="academic_hunter.cache"):
            assert cache.get("key") is None

        assert any("Cache read error" in record.getMessage() for record in caplog.records), (
            "the corrupt cache was indistinguishable from a miss"
        )
    finally:
        os.unlink(path)


def test_a_plain_miss_is_not_reported_as_an_error(caplog):
    """Only a failure is a failure: a key that was never stored is normal."""
    cache, path = _make_cache()
    try:
        with caplog.at_level(logging.WARNING, logger="academic_hunter.cache"):
            assert cache.get("never-stored") is None

        assert not caplog.records, f"a miss was logged: {caplog.records}"
    finally:
        os.unlink(path)


def test_cache_insert_or_replace():
    """INSERT OR REPLACE works as expected for same key."""
    cache, path = _make_cache()
    try:
        cache.set("dup", "first")
        cache.set("dup", "second")
        assert cache.get("dup") == "second"
    finally:
        os.unlink(path)


def test_cache_persists_to_disk():
    """Cache persists values to a real SQLite file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        cache = SQLiteCache(db_path=db_path)
        cache.set("persist", "disk_value")
        cache2 = SQLiteCache(db_path=db_path)
        assert cache2.get("persist") == "disk_value"
    finally:
        os.unlink(db_path)
