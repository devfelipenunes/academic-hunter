"""An environment override belongs to the process, not to the config file.

Two failures meet here, and both were silent.

An override was written straight into the dict the loader had read from disk, so
the next ``save()`` persisted it. A credential supplied through the environment
ended up on disk, and a value set for a single run outlived it.

And the coercion turned ``=1`` into ``int 1``, which ``fulltext.enabled``
rejects — it accepts only a real boolean. The spelling an operator is most likely
to reach for therefore switched the stage *off*, without a word.
"""

import json

import pytest

from academic_hunter.core.infra.config import HunterConfig

SECRET = "env-credential-value"


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "settings": {
            "start_year": 2015,
            "semantic_scholar_api_key": "",
            "limit_per_query": 100,
            "fulltext": {"enabled": False},
        },
        "anchors": {"cat": ["ledger"]},
        "technical_strings": {},
        "technical_weights": {},
    }))
    return path


@pytest.fixture
def config(config_path):
    return HunterConfig(config_path=str(config_path))


def _reload(config_path):
    return HunterConfig(config_path=str(config_path))


def _on_disk(config_path):
    return json.loads(config_path.read_text())


def test_one_switches_a_stage_on(monkeypatch, config):
    """`=1` is the spelling a shell and a systemd unit both use for true."""
    monkeypatch.setenv("ACADEMIC_HUNTER_SETTINGS__FULLTEXT__ENABLED", "1")

    assert _reload(config.config_path).fulltext_config()["enabled"] is True


def test_the_word_true_still_works(monkeypatch, config_path):
    monkeypatch.setenv("ACADEMIC_HUNTER_SETTINGS__FULLTEXT__ENABLED", "true")

    assert _reload(config_path).fulltext_config()["enabled"] is True


def test_an_integer_setting_keeps_its_type(monkeypatch, config_path):
    """`=1` must stay an integer where an integer is what the file holds."""
    monkeypatch.setenv("ACADEMIC_HUNTER_SETTINGS__LIMIT_PER_QUERY", "7")

    value = _reload(config_path).settings["limit_per_query"]

    assert value == 7
    assert not isinstance(value, bool)


def test_the_override_reaches_the_live_settings(monkeypatch, config_path):
    monkeypatch.setenv("ACADEMIC_HUNTER_SETTINGS__SEMANTIC_SCHOLAR_API_KEY", SECRET)

    assert _reload(config_path).settings["semantic_scholar_api_key"] == SECRET


def test_a_credential_from_the_environment_never_reaches_the_file(
    monkeypatch, config_path
):
    monkeypatch.setenv("ACADEMIC_HUNTER_SETTINGS__SEMANTIC_SCHOLAR_API_KEY", SECRET)
    made = _reload(config_path)

    made.save()

    assert SECRET not in config_path.read_text()
    assert _on_disk(config_path)["settings"]["semantic_scholar_api_key"] == ""


def test_saving_restores_every_overridden_value(monkeypatch, config_path):
    monkeypatch.setenv("ACADEMIC_HUNTER_SETTINGS__FULLTEXT__ENABLED", "1")
    monkeypatch.setenv("ACADEMIC_HUNTER_SETTINGS__LIMIT_PER_QUERY", "7")
    monkeypatch.setenv("ACADEMIC_HUNTER_ANCHORS__CAT", "ledger")
    made = _reload(config_path)

    made.save()

    written = _on_disk(config_path)
    assert written["settings"]["fulltext"]["enabled"] is False
    assert written["settings"]["limit_per_query"] == 100
    assert written["anchors"]["cat"] == ["ledger"]


def test_saving_leaves_the_running_config_overridden(monkeypatch, config_path):
    """Restoring the file's value must not reach back into the live settings."""
    monkeypatch.setenv("ACADEMIC_HUNTER_SETTINGS__FULLTEXT__ENABLED", "1")
    made = _reload(config_path)

    made.save()

    assert made.fulltext_config()["enabled"] is True


def test_a_path_the_file_lacks_is_not_written(monkeypatch, config_path):
    """The file had no `api_keys`; saving must not invent one from the override."""
    monkeypatch.setenv("ACADEMIC_HUNTER_SETTINGS__API_KEYS__CORE", "core-value")
    made = _reload(config_path)

    assert made.settings["api_keys"]["core"] == "core-value"
    made.save()

    assert _on_disk(config_path)["settings"].get("api_keys") in (None, {})
