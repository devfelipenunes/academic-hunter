"""Recarregar a config tem de alcançar quem a lê.

O `scorer` e os conectores são construídos **uma vez**, com os dicionários do
config como argumentos. `load()` reatribuía esses dicionários, então um reload
trocava o que o config continha e deixava todo mundo lendo o anterior.

`state.reset` documenta exatamente esse perigo para `query_history` — "cleared,
not rebound" — e o config não recebia o mesmo tratamento.
"""

import json
import os
import time

import pytest

from academic_hunter import AcademicHunter


def _write(path, weights, *, newer_by=0.0):
    """Write the config, stamped `newer_by` seconds ahead of now.

    `load()` skips a file it considers fresh within a 100 ms tolerance of the
    moment it last loaded, and a write landing in that window is not picked up.
    Stamping the mtime keeps the test deterministic instead of sleeping.
    """
    path.write_text(
        json.dumps({
            "settings": {"min_relevance_score": 0.0, "start_year": 2024},
            "anchors": {"A": ["ledger"]},
            "technical_strings": {"T": ["throughput"]},
            "technical_weights": weights,
        }),
        encoding="utf-8",
    )
    stamp = time.time() + newer_by
    os.utime(path, (stamp, stamp))


@pytest.fixture
def hunter(tmp_path):
    config_path = tmp_path / "config.json"
    _write(config_path, {"ledger": 1.0})
    return AcademicHunter(config_path=str(config_path), output_dir=str(tmp_path)), config_path


def test_reloading_reaches_the_scorer(hunter):
    """`config.load()` rebound the dictionaries; the scorer held the old ones."""
    instance, config_path = hunter
    assert instance.scorer.tech_weights == {"ledger": 1.0}

    _write(config_path, {"ledger": 9.0}, newer_by=1.0)
    instance.load_config()

    assert instance.scorer.tech_weights == {"ledger": 9.0}, (
        "the scorer is still reading the configuration from before the reload"
    )


def test_reloading_reaches_the_connectors(hunter):
    """They are constructed with the config's `settings` dict as an argument.

    The change comes from the **file**, not from mutating the live dict — which
    would be visible to everyone holding it and would prove nothing about the
    reload.
    """
    instance, config_path = hunter
    connector = next(iter(instance.connectors.values()))
    before = connector.settings.get("user_email")

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["settings"]["user_email"] = "changed@example.com"
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    stamp = time.time() + 1.0
    os.utime(config_path, (stamp, stamp))

    instance.load_config()

    assert before != "changed@example.com", "the fixture already had this value"
    assert connector.settings["user_email"] == "changed@example.com", (
        "the connectors are still reading the settings from before the reload"
    )


def test_reloading_actually_changes_what_the_config_reports(hunter):
    """The property above must not be bought by never reloading at all."""
    instance, config_path = hunter

    _write(config_path, {"ledger": 9.0}, newer_by=1.0)
    instance.load_config()

    assert instance.config.tech_weights == {"ledger": 9.0}
