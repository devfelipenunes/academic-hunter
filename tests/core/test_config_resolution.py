"""``HunterConfig`` reads and writes wherever the resolver says, and nowhere else.

The failure this guards against is specific: an installed copy used to write its
config back into ``site-packages``, which is read-only on many systems and is
discarded on every upgrade on the rest — so the researcher's topic survived
until the next ``uvx`` rebuild and then silently did not.
"""

import json
from pathlib import Path

import pytest

from academic_hunter.core.infra import paths
from academic_hunter.core.infra.config import HunterConfig


@pytest.fixture(autouse=True)
def _no_ambient_resolution(tmp_path, monkeypatch):
    for name in (paths.CONFIG_ENV, paths.DATA_ENV, paths.PROJECT_ENV,
                 "XDG_CONFIG_HOME", "XDG_DATA_HOME"):
        monkeypatch.delenv(name, raising=False)
    neutral = tmp_path / "cwd"
    neutral.mkdir()
    monkeypatch.chdir(neutral)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


def test_an_explicit_path_still_wins(tmp_path):
    """Callers that pass a path — mostly tests — are unaffected by the resolver."""
    target = tmp_path / "chosen.json"
    target.write_text(json.dumps({"settings": {}, "anchors": {}}), encoding="utf-8")

    config = HunterConfig(str(target))

    assert config.config_path == target
    assert config.config_origin == paths.ORIGIN_EXPLICIT


def test_no_argument_resolves_through_the_search_order(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "checkout_root", lambda: None)

    config = HunterConfig()

    assert config.config_path == paths.packaged_default_path()
    assert config.config_origin == paths.ORIGIN_PACKAGED


def test_the_config_reports_the_file_it_loaded(tmp_path, monkeypatch):
    target = Path.cwd() / paths.CONFIG_FILENAME
    target.write_text(
        json.dumps({"settings": {}, "anchors": {"Topic": ["graphs"]}}), encoding="utf-8"
    )

    config = HunterConfig()

    assert config.config_path == target
    assert config.config_origin == paths.ORIGIN_CWD
    assert config.anchors == {"Topic": ["graphs"]}


def test_a_missing_config_says_which_choice_failed(tmp_path, monkeypatch):
    """The message has to name the variable that is wrong, or it is unactionable."""
    monkeypatch.setenv(paths.CONFIG_ENV, str(tmp_path / "gone.json"))

    with pytest.raises(FileNotFoundError, match=paths.CONFIG_ENV):
        HunterConfig()


def test_a_config_that_vanishes_after_resolution_names_its_rung(tmp_path, monkeypatch):
    """The other failure: the file was found, then deleted before the read."""
    target = Path.cwd() / paths.CONFIG_FILENAME
    target.write_text(json.dumps({"settings": {}}), encoding="utf-8")
    config = HunterConfig()

    target.unlink()

    with pytest.raises(FileNotFoundError, match="chosen by"):
        config.load(force=True)


# ── the packaged default is read-only ─────────────────────────────


def test_saving_the_default_materialises_it_outside_the_package(tmp_path, monkeypatch):
    """Saving what was never written by the user must not write into the install."""
    monkeypatch.setattr(paths, "checkout_root", lambda: None)
    config = HunterConfig()
    assert config.config_origin == paths.ORIGIN_PACKAGED

    config.anchors = {"Topic": ["zero knowledge proof"]}
    config.save()

    expected = paths.user_config_file()
    assert config.config_path == expected
    assert config.config_origin == paths.ORIGIN_USER_CONFIG
    assert expected.is_file()

    written = json.loads(expected.read_text(encoding="utf-8"))
    assert written["anchors"] == {"Topic": ["zero knowledge proof"]}

    packaged = json.loads(paths.packaged_default_path().read_text(encoding="utf-8"))
    assert packaged["anchors"] == {}, "the packaged default was overwritten"


def test_a_saved_default_is_then_read_back(tmp_path, monkeypatch):
    """The redirect has to stick: the next process reads the same file."""
    monkeypatch.setattr(paths, "checkout_root", lambda: None)
    config = HunterConfig()
    config.anchors = {"Topic": ["graph neural networks"]}
    config.save()

    reopened = HunterConfig()

    assert reopened.config_path == paths.user_config_file()
    assert reopened.config_origin == paths.ORIGIN_USER_CONFIG
    assert reopened.anchors == {"Topic": ["graph neural networks"]}


def test_saving_a_config_the_user_owns_leaves_it_where_it_is(tmp_path):
    target = tmp_path / "mine.json"
    target.write_text(json.dumps({"settings": {}, "anchors": {}}), encoding="utf-8")
    config = HunterConfig(str(target))

    config.anchors = {"Topic": ["anything"]}
    config.save()

    assert config.config_path == target
    assert json.loads(target.read_text(encoding="utf-8"))["anchors"] == {
        "Topic": ["anything"]
    }


# ── is_scorable, which is what stops a silent empty run ───────────


def test_the_packaged_default_is_not_scorable(monkeypatch):
    """The neutral default has no topic, and that has to be detectable.

    Without this, ``run_search`` against the default queries every source for
    nothing and reports success.
    """
    monkeypatch.setattr(paths, "checkout_root", lambda: None)
    config = HunterConfig()

    assert config.config_origin == paths.ORIGIN_PACKAGED
    assert config.is_scorable() is False


def test_anchors_make_a_config_scorable(tmp_path):
    target = tmp_path / "c.json"
    target.write_text(
        json.dumps({"settings": {}, "anchors": {"Topic": ["ledgers"]}}), encoding="utf-8"
    )

    assert HunterConfig(str(target)).is_scorable() is True


def test_weights_alone_are_not_scorable(tmp_path):
    """Weights with no anchors issue no query, so they are not scorable.

    This test used to assert the opposite. The pipeline iterates anchors --
    ``for anchor_cat, anchor_list in hunter.anchors.items()`` -- and the
    keyword-only branch is nested inside that loop, so an empty ``anchors``
    skips every connector, keyword-only ones included. A config like this one
    passed the old guard and then queried nothing at all, which is the silent
    empty run the guard exists to stop.
    """
    target = tmp_path / "c.json"
    target.write_text(
        json.dumps({"settings": {}, "technical_weights": {"iso 20022": 2.0}}),
        encoding="utf-8",
    )

    assert HunterConfig(str(target)).is_scorable() is False


# ── the resolver's variables are not config overrides ─────────────


def test_the_path_variables_do_not_leak_into_settings(tmp_path, monkeypatch):
    """``ACADEMIC_HUNTER_CONFIG`` would otherwise become ``settings.config``.

    Every ``ACADEMIC_HUNTER_*`` variable is a dot-path override applied to the
    loaded config, so the two that name files are reserved by name.
    """
    target = tmp_path / "c.json"
    target.write_text(json.dumps({"settings": {}}), encoding="utf-8")
    monkeypatch.setenv(paths.CONFIG_ENV, str(target))
    monkeypatch.setenv(paths.DATA_ENV, str(tmp_path / "data"))

    config = HunterConfig()

    assert "config" not in config.settings
    assert "data_dir" not in config.settings


def test_an_unrelated_variable_is_still_an_override(tmp_path, monkeypatch):
    """The reserved names are the exception; every other one still works."""
    target = tmp_path / "c.json"
    target.write_text(json.dumps({"settings": {}}), encoding="utf-8")
    monkeypatch.setenv(paths.CONFIG_ENV, str(target))
    monkeypatch.setenv("ACADEMIC_HUNTER_SETTINGS__START_YEAR", "2019")

    assert HunterConfig().settings["start_year"] == 2019
