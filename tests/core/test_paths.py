"""The config and data search order, which is what makes an installed copy work.

Each rung is asserted on its own and in the presence of the rungs below it: a
rung that only works in isolation would still send an installed server to a
checkout it does not have, or scatter ``.academic_hunter/`` through whatever
directory the MCP client happened to spawn it in.
"""

import json
from pathlib import Path

import pytest

from academic_hunter.core.infra import paths


@pytest.fixture(autouse=True)
def _no_ambient_resolution(tmp_path, monkeypatch):
    """Every rung starts from nothing, with a neutral cwd.

    The variables are read by ``resolve_*`` directly, so a developer's exported
    ``ACADEMIC_HUNTER_CONFIG`` would otherwise decide what these tests measure.
    """
    for name in (paths.CONFIG_ENV, paths.DATA_ENV, paths.PROJECT_ENV, "XDG_CONFIG_HOME", "XDG_DATA_HOME"):
        monkeypatch.delenv(name, raising=False)
    neutral = tmp_path / "cwd"
    neutral.mkdir()
    monkeypatch.chdir(neutral)


@pytest.fixture
def installed(monkeypatch):
    """Stand in for a pip/uvx install, where no pyproject.toml sits above the package.

    The suite runs from the checkout, so ``checkout_root()`` always finds one and
    would outrank the rungs these tests are about. Neutralising it is what makes
    them measure the installed case rather than the developer's.
    """
    monkeypatch.setattr(paths, "checkout_root", lambda: None)
    return paths


def _write_config(directory: Path, **overrides) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "settings": {"user_email": overrides.pop("user_email", "")},
        "anchors": overrides.pop("anchors", {}),
        "technical_strings": {},
        "technical_weights": overrides.pop("technical_weights", {}),
        "context_rules": {},
    }
    payload.update(overrides)
    target = directory / paths.CONFIG_FILENAME
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


# ── config: the rungs, in order ───────────────────────────────────


def test_env_names_the_config(tmp_path, monkeypatch):
    explicit = _write_config(tmp_path / "explicit")
    monkeypatch.setenv(paths.CONFIG_ENV, str(explicit))

    found = paths.resolve_config_path()

    assert found.path == explicit
    assert found.origin == paths.ORIGIN_ENV


def test_env_beats_a_config_in_the_current_directory(tmp_path, monkeypatch):
    explicit = _write_config(tmp_path / "explicit")
    _write_config(Path.cwd())
    monkeypatch.setenv(paths.CONFIG_ENV, str(explicit))

    assert paths.resolve_config_path().path == explicit


def test_env_pointing_at_nothing_is_an_error_not_a_fallback(tmp_path, monkeypatch):
    """A typo must not silently become "use some other config"."""
    _write_config(Path.cwd())
    monkeypatch.setenv(paths.CONFIG_ENV, str(tmp_path / "typo.json"))

    with pytest.raises(FileNotFoundError, match="not a file"):
        paths.resolve_config_path()


def test_current_directory_wins_over_the_rest(tmp_path, monkeypatch):
    expected = _write_config(Path.cwd())
    _write_config(tmp_path / "project")
    monkeypatch.setenv(paths.PROJECT_ENV, str(tmp_path / "project"))

    found = paths.resolve_config_path()

    assert found.path == expected
    assert found.origin == paths.ORIGIN_CWD


def test_a_config_inside_the_state_directory_is_found(tmp_path, monkeypatch):
    expected = _write_config(Path.cwd() / paths.DATA_DIRNAME)

    found = paths.resolve_config_path()

    assert found.path == expected
    assert found.origin == paths.ORIGIN_CWD


def test_claude_project_dir_wins_over_the_user_config(tmp_path, monkeypatch):
    project = tmp_path / "project"
    expected = _write_config(project)
    monkeypatch.setenv(paths.PROJECT_ENV, str(project))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    _write_config(tmp_path / "xdg" / paths.APP_DIRNAME)

    found = paths.resolve_config_path()

    assert found.path == expected
    assert found.origin == paths.ORIGIN_CLAUDE_PROJECT


def test_user_config_is_reached_when_nothing_else_matches(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    expected = _write_config(tmp_path / "xdg" / paths.APP_DIRNAME)

    found = paths.resolve_config_path()

    assert found.path == expected
    assert found.origin == paths.ORIGIN_USER_CONFIG


def test_user_config_honours_the_xdg_default_when_unset(monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    assert paths.user_config_file() == (Path("~/.config").expanduser() / paths.APP_DIRNAME / paths.CONFIG_FILENAME)


def test_a_relative_xdg_home_is_ignored(monkeypatch):
    """The spec requires an absolute path; a relative one would follow the cwd."""
    monkeypatch.setenv("XDG_CONFIG_HOME", "relative/path")

    assert paths.user_config_file() == (Path("~/.config").expanduser() / paths.APP_DIRNAME / paths.CONFIG_FILENAME)


def test_the_packaged_default_is_the_last_resort(tmp_path, installed):
    """Nothing was found, so the packaged file answers — and says so."""
    found = paths.resolve_config_path()

    assert found.path == paths.packaged_default_path()
    assert found.origin == paths.ORIGIN_PACKAGED
    assert found.is_default


def test_the_packaged_default_exists_and_is_neutral():
    """The last resort has to exist, and must not be anybody's research topic."""
    default = json.loads(paths.packaged_default_path().read_text(encoding="utf-8"))

    assert default["anchors"] == {}
    assert default["technical_weights"] == {}
    assert default["technical_strings"] == {}
    assert default["settings"]["user_email"] == ""


def test_the_user_config_is_not_the_packaged_default():
    """``save()`` redirects into the package; the resolver must not read there."""
    assert paths.user_config_file() != paths.packaged_default_path()
    assert not paths.is_inside_package(paths.user_config_file())
    assert paths.is_inside_package(paths.packaged_default_path())


# ── data: the rungs, in order ─────────────────────────────────────


def test_data_env_names_the_project_directory(tmp_path, monkeypatch):
    base = tmp_path / "explicit"
    monkeypatch.setenv(paths.DATA_ENV, str(base))

    found = paths.resolve_location()

    assert found.base == base
    assert found.data_dir == base / paths.DATA_DIRNAME
    assert found.results_dir == base / paths.RESULTS_DIRNAME
    assert found.origin == paths.ORIGIN_ENV


def test_data_env_pointing_at_a_file_is_an_error(tmp_path, monkeypatch):
    target = tmp_path / "a-file"
    target.write_text("")
    monkeypatch.setenv(paths.DATA_ENV, str(target))

    with pytest.raises(NotADirectoryError, match="which is a file"):
        paths.resolve_location()


def test_a_bare_directory_is_not_a_project(tmp_path, monkeypatch, installed):
    """Without a marker, an installed server must not claim the cwd as state.

    This is the uvx case: the client spawns the server somewhere arbitrary, and
    writing ``.academic_hunter/`` and ``results/`` there would leave the user's
    directories littered with a state they cannot find again.
    """
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    found = paths.resolve_location()

    assert found.base == tmp_path / "xdg" / paths.APP_DIRNAME
    assert found.origin == paths.ORIGIN_USER_DATA


def test_a_state_directory_marks_the_project(tmp_path, monkeypatch):
    (Path.cwd() / paths.DATA_DIRNAME).mkdir()

    found = paths.resolve_location()

    assert found.base == Path.cwd()
    assert found.origin == paths.ORIGIN_CWD


def test_a_config_alone_marks_the_project(tmp_path, monkeypatch):
    _write_config(Path.cwd())

    found = paths.resolve_location()

    assert found.base == Path.cwd()
    assert found.origin == paths.ORIGIN_CWD


def test_claude_project_dir_is_used_when_it_carries_the_marker(tmp_path, monkeypatch):
    project = tmp_path / "project"
    (project / paths.DATA_DIRNAME).mkdir(parents=True)
    monkeypatch.setenv(paths.PROJECT_ENV, str(project))

    found = paths.resolve_location()

    assert found.base == project
    assert found.origin == paths.ORIGIN_CLAUDE_PROJECT


def test_an_unmarked_claude_project_dir_is_ignored(tmp_path, monkeypatch, installed):
    """The variable proving nothing about layout must not win over the XDG dir."""
    monkeypatch.setenv(paths.PROJECT_ENV, str(tmp_path / "bare"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    assert paths.resolve_location().origin == paths.ORIGIN_USER_DATA


def test_xdg_data_home_is_honoured(tmp_path, monkeypatch, installed):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    assert paths.resolve_location().base == tmp_path / "xdg" / paths.APP_DIRNAME


def test_the_history_database_lives_under_the_data_dir(tmp_path, monkeypatch):
    base = tmp_path / "project"
    monkeypatch.setenv(paths.DATA_ENV, str(base))

    assert paths.resolve_location().history_db == base / paths.DATA_DIRNAME / "mcp_history.db"


def test_ensure_data_dir_creates_every_parent(tmp_path, monkeypatch):
    """A fresh XDG tree does not exist yet; ``mkdir`` has to build it."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg" / "deep"))

    created = paths.ensure_data_dir()

    assert created.is_dir()
    assert created == paths.resolve_location().data_dir


# ── the checkout stays the checkout ───────────────────────────────


def test_the_checkout_is_found_from_the_package_file():
    """Development keeps working: run from a clone and the clone is the project."""
    root = paths.checkout_root()

    assert root is not None
    assert (root / "pyproject.toml").is_file()


def test_a_clone_resolves_to_itself():
    """Development compatibility: run from the repo and the repo is the project.

    This is what keeps an existing ``.academic_hunter/chroma_db`` and ``results/``
    reachable after the resolver was introduced.
    """
    found = paths.resolve_location()

    assert found.origin == paths.ORIGIN_CHECKOUT
    assert found.base == paths.checkout_root()
    assert found.data_dir.is_dir(), "the checkout's existing state directory"


def test_a_clone_obeys_an_explicit_choice_over_itself(tmp_path, monkeypatch):
    """The checkout is a fallback, not an override."""
    base = tmp_path / "explicit"
    monkeypatch.setenv(paths.DATA_ENV, str(base))

    found = paths.resolve_location()

    assert found.origin == paths.ORIGIN_ENV
    assert found.base == base


def test_a_clone_obeys_the_user_config_over_its_own(tmp_path, monkeypatch):
    """A clone with no config.json of its own must not shadow the user's."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    expected = _write_config(tmp_path / "xdg" / paths.APP_DIRNAME)

    found = paths.resolve_config_path()

    assert found.path == expected
    assert found.origin == paths.ORIGIN_USER_CONFIG


# ── describe(), which is what the server reports ──────────────────


def test_describe_names_both_resolutions(tmp_path, monkeypatch, installed):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    described = paths.describe()

    assert described["config"]["origin"] == paths.ORIGIN_PACKAGED
    assert described["config"]["is_default"] is True
    assert described["data"]["origin"] == paths.ORIGIN_USER_DATA
    assert described["data"]["data_dir"].endswith(paths.DATA_DIRNAME)


def test_describe_reports_a_broken_choice_instead_of_raising(monkeypatch):
    """It feeds server_status, which must answer even when the config is wrong."""
    monkeypatch.setenv(paths.CONFIG_ENV, "/nonexistent/config.json")

    described = paths.describe()

    assert "error" in described["config"]
    assert "data" in described
