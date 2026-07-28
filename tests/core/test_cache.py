"""Tests for SQLiteCache — persistent request caching."""
import os
import tempfile
from academic_hunter.core.infra.cache import SQLiteCache


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


def test_cache_get_error_returns_none():
    """get returns None when database is corrupted."""
    cache, path = _make_cache()
    try:
        # Corrupt the database file
        with open(path, "w") as f:
            f.write("not a valid sqlite file")
        assert cache.get("key") is None
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
