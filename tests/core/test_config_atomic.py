"""A config que some no meio da escrita derruba tudo que depende dela.

`save()` abre o arquivo em `"w"`, o que **trunca antes de escrever qualquer
coisa**. Uma falha na serialização deixa o arquivo vazio, e a config é lida por
`read_config`, por `list_config_history` e por toda ferramenta que carrega
configuração — inclusive de outro processo, a qualquer momento.
"""

import json
import os
import stat
from pathlib import Path

import pytest

from academic_hunter.core.infra import HunterConfig
from academic_hunter.core.infra.atomic import write_json_atomically


def _loaded(tmp_path, email="old@example.com"):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"settings": {"user_email": email}}), encoding="utf-8")
    config = HunterConfig(config_path=str(path))
    config.load(force=True)
    return path, config


def test_a_save_that_fails_does_not_destroy_the_previous_config(tmp_path, monkeypatch):
    path, config = _loaded(tmp_path)
    config.settings["user_email"] = "new@example.com"

    def explode(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(json, "dump", explode)
    monkeypatch.setattr(json, "dumps", explode)

    with pytest.raises(OSError):
        config.save()

    assert json.loads(path.read_text(encoding="utf-8"))["settings"]["user_email"] == (
        "old@example.com"
    ), "the previous config was destroyed by a save that never completed"


def test_a_save_that_succeeds_round_trips(tmp_path):
    path, config = _loaded(tmp_path)
    config.settings["user_email"] = "new@example.com"

    config.save()

    reloaded = HunterConfig(config_path=str(path))
    reloaded.load(force=True)
    assert reloaded.settings["user_email"] == "new@example.com"


def test_a_broken_config_says_which_file_is_broken(tmp_path):
    """`json.load` raising on its own names neither the file nor the reason.

    A config left half-written by a crash is exactly the case someone has to
    diagnose, and "Expecting property name" alone does not say which file.
    """
    path = tmp_path / "config.json"
    path.write_text('{"settings": {"user_email": "a@b.c"', encoding="utf-8")

    with pytest.raises(ValueError, match="config.json"):
        HunterConfig(config_path=str(path))


def test_a_config_that_says_nothing_about_the_topic_gets_no_topic(tmp_path):
    """A missing `keyword_only_terms` injected a fintech default.

    `ledger`, `payment`, `interoperability`, `settlement`, `blockchain`, filed
    under "Consolidated_Fintech" — handed to anyone whose config did not mention
    the field, whatever they were researching. Nothing in the pipeline reads it,
    so it changed no search and appeared only in `read_config`, where it reads as
    configuration the researcher had set.
    """
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"settings": {"user_email": "a@b.c"}}), encoding="utf-8")

    config = HunterConfig(config_path=str(path))

    assert config.keyword_only_terms == []
    assert config.keyword_only_category == ""


def test_the_rename_keeps_the_mode_the_file_had(tmp_path):
    """A config tightened to 0600 came back 0644 on the next save.

    The temp file was created with `write_text`, which takes the umask default,
    and `rename` carries the temp file's mode onto the target. So the one
    permission that matters for a file holding API keys was silently loosened by
    the tool that writes it.
    """
    path = tmp_path / "config.json"
    write_json_atomically(path, {"a": 1})
    os.chmod(path, 0o600)

    write_json_atomically(path, {"a": 2})

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_two_writers_never_share_the_temp_file(tmp_path, monkeypatch):
    """`<name>.part` was one fixed path, so concurrent writers clobbered it."""
    target = tmp_path / "config.json"
    used = []
    real_replace = Path.replace

    def record(self, other):
        used.append(self)
        return real_replace(self, other)

    monkeypatch.setattr(Path, "replace", record)
    write_json_atomically(target, {"writer": 1})
    write_json_atomically(target, {"writer": 2})

    assert used[0] != used[1], "both writers staged through the same temp file"
    assert not list(tmp_path.glob("*.part")), "a temp file outlived its write"
