"""A `save()` must not delete what it does not understand.

The writer kept only the top-level keys beginning with ``_`` and rebuilt the rest
from its own list of sections, so anything else in the file was dropped. A
version stamp, a block belonging to another tool, a note to self — any of them
disappeared the first time the config was written back, which is a
``save()`` reachable from the MCP tools.
"""

import json

import pytest

from academic_hunter.core.infra.config import HunterConfig

EXTRA = {"version": "1.2.0", "editor": {"theme": "dark"}}


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "settings": {"start_year": 2015},
        "anchors": {"cat": ["ledger"]},
        "technical_strings": {},
        "technical_weights": {},
        "context_rules": {"drex": ["cbdc"]},
        **EXTRA,
    }))
    return path


def test_unknown_keys_survive_a_save(config_path):
    HunterConfig(config_path=str(config_path)).save()

    written = json.loads(config_path.read_text())
    for key, value in EXTRA.items():
        assert written.get(key) == value, f"{key!r} was dropped by save()"


def test_the_known_sections_are_still_written(config_path):
    """Preserving the rest must not mean copying the whole file through."""
    made = HunterConfig(config_path=str(config_path))
    made.anchors["cat"] = ["consensus"]

    made.save()

    assert json.loads(config_path.read_text())["anchors"]["cat"] == ["consensus"]


def test_the_old_top_level_rules_are_not_brought_back(config_path):
    """`context_rules` moved inside `settings`; reviving the old copy is the bug."""
    HunterConfig(config_path=str(config_path)).save()

    written = json.loads(config_path.read_text())
    assert "context_rules" not in written
    assert written["settings"]["context_rules"] == {"drex": ["cbdc"]}
