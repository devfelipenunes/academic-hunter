"""A folder called ``testes`` must not switch the request cache off.

``AcademicHunter.__init__`` disabled the cache when the config path merely
*contained* the substring ``test``. So a project kept in a directory named
``testes/`` lost its cache in silence and went back to the network on every
call -- and the operator had no way to see why, because nothing was logged.

The question the switch means to ask is whether this process is a test run. The
two ``sys.modules`` clauses answer that; the path never did.
"""

import json
import sys

import pytest

from academic_hunter import AcademicHunter


@pytest.fixture
def as_production(monkeypatch):
    """The process as a non-test run sees it: no ``pytest``, no ``unittest``."""
    for name in ("pytest", "unittest"):
        monkeypatch.delitem(sys.modules, name, raising=False)


def _config(tmp_path, directory, filename="config.json"):
    folder = tmp_path / directory
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    path.write_text(json.dumps({
        "settings": {"start_year": 2024},
        "anchors": {}, "technical_strings": {}, "technical_weights": {},
    }))
    return path


def _hunter(config_path, tmp_path):
    return AcademicHunter(config_path=str(config_path), output_dir=str(tmp_path / "out"))


def test_a_directory_named_testes_does_not_disable_the_cache(tmp_path, as_production):
    hunter = _hunter(_config(tmp_path, "testes"), tmp_path)

    assert hunter.use_cache is True


def test_a_config_named_config_test_json_does_not_disable_the_cache(tmp_path, as_production):
    """The other half of the same substring: the file name, not the folder."""
    hunter = _hunter(_config(tmp_path, "proj", filename="config.test.json"), tmp_path)

    assert hunter.use_cache is True


def test_the_connectors_get_the_cache_the_hunter_reports(tmp_path, as_production):
    """The flag is not decoration: it is what the connectors are built with."""
    hunter = _hunter(_config(tmp_path, "testes"), tmp_path)

    assert hunter.use_cache is True
    assert all(conn.use_cache is True for conn in hunter.connectors.values())


def test_a_test_process_still_disables_the_cache(tmp_path):
    """The clause that was meant, kept: this very process is a test run."""
    hunter = _hunter(_config(tmp_path, "proj"), tmp_path)

    assert hunter.use_cache is False


def test_an_explicit_false_still_wins(tmp_path, as_production):
    hunter = AcademicHunter(
        config_path=str(_config(tmp_path, "proj")),
        output_dir=str(tmp_path / "out"),
        use_cache=False,
    )

    assert hunter.use_cache is False
