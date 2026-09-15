"""A config que some no meio da escrita derruba tudo que depende dela.

`save()` abre o arquivo em `"w"`, o que **trunca antes de escrever qualquer
coisa**. Uma falha na serialização deixa o arquivo vazio, e a config é lida por
`read_config`, por `list_config_history` e por toda ferramenta que carrega
configuração — inclusive de outro processo, a qualquer momento.
"""

import json

import pytest

from academic_hunter.core.infra import HunterConfig


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
        HunterConfig(config_path=str(path))  # the constructor loads


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
