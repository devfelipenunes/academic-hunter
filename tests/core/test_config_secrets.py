"""Credentials must never be serialised back to a caller.

The live ``settings`` still carries the real values — the connectors read them
from there — so the masking has to happen on the way out, not in the config.
"""

import json

import pytest

from academic_hunter.core.infra.config import REDACTED, HunterConfig

SECRET = "s2k-secret-value"
NESTED_SECRET = "core-nested-secret"

CONFIG = {
    "settings": {
        "start_year": 2021,
        "min_inclusion_score": 5.0,
        "ranking_query": "How does X meet Y?",
        "user_email": "someone@example.org",
        "semantic_scholar_api_key": SECRET,
        "api_keys": {
            "semantic_scholar": SECRET,
            "core": NESTED_SECRET,
            "openalex": "",
        },
    },
    "anchors": {"cat": ["blockchain"]},
    "technical_strings": {"cat": ["ledger"]},
    "technical_weights": {"blockchain": 5.0},
    "context_rules": {"blockchain": ["ledger"]},
}


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(CONFIG))
    return HunterConfig(config_path=str(path))


def test_a_flat_credential_is_masked(config):
    assert config.public_settings()["semantic_scholar_api_key"] == REDACTED


def test_nested_credentials_are_masked(config):
    keys = config.public_settings()["api_keys"]

    assert keys["semantic_scholar"] == REDACTED
    assert keys["core"] == REDACTED


def test_an_unset_credential_stays_empty(config):
    """An absent key must not become a placeholder: that would claim one exists."""
    assert config.public_settings()["api_keys"]["openalex"] == ""


def test_non_secret_settings_pass_through(config):
    assert config.public_settings()["start_year"] == 2021


def test_the_live_settings_keep_the_real_values(config):
    """Masking is for the copy; the connectors still read the real thing."""
    config.public_settings()

    assert config.settings["semantic_scholar_api_key"] == SECRET
    assert config.settings["api_keys"]["core"] == NESTED_SECRET


def test_serialising_the_public_settings_leaks_nothing(config):
    """The end-to-end property: whatever a caller receives, the secrets are absent."""
    payload = json.dumps(config.public_settings())

    assert SECRET not in payload
    assert NESTED_SECRET not in payload


def test_the_snapshot_that_lands_in_the_run_carries_no_credential(config):
    """The archive is the file people attach to a thesis or mail to an advisor.

    It goes to disk under ``results/``, which no masking step ever sees, so the
    filtering has to happen where the snapshot is built.
    """
    payload = json.dumps(config.run_snapshot(), ensure_ascii=False)

    assert SECRET not in payload
    assert NESTED_SECRET not in payload
    assert "api_keys" not in payload
    assert "user_email" not in payload


def test_the_archived_settings_are_exactly_the_declared_ones(config):
    """A positive list fails closed: a new setting is archived once declared.

    The alternative — excluding credentials by name — has to guess every name
    at every depth, forever, and gets it wrong the first time one is added.
    """
    archived = config.run_snapshot()["settings"]

    assert set(archived) <= set(HunterConfig.RUN_ARCHIVE_SETTINGS)
    assert archived["min_inclusion_score"] == 5.0
    assert archived["ranking_query"] == "How does X meet Y?"
    assert archived["start_year"] == 2021


def test_the_snapshot_keeps_the_weights_and_the_rules(config):
    """These two are the whole point: what decides admission and score."""
    snapshot = config.run_snapshot()

    assert snapshot["technical_weights"] == {"blockchain": 5.0}
    assert snapshot["context_rules"] == {"blockchain": ["ledger"]}
    assert snapshot["anchors"] == {"cat": ["blockchain"]}


def test_the_snapshot_is_a_copy_and_not_a_view(config):
    """``update_config`` mutates settings in place, and the PRISMA export runs after.

    A reference would let a change of topic rewrite the record of a run that had
    already finished.
    """
    snapshot = config.run_snapshot()

    config.settings["min_inclusion_score"] = 99.0
    config.settings["ranking_query"] = "A different topic"
    config.tech_weights["blockchain"] = 1.0

    assert snapshot["settings"]["min_inclusion_score"] == 5.0
    assert snapshot["settings"]["ranking_query"] == "How does X meet Y?"
    assert snapshot["technical_weights"] == {"blockchain": 5.0}


def test_the_same_configuration_fingerprints_the_same(config):
    assert config.run_snapshot()["config_fingerprint"] == (
        config.run_snapshot()["config_fingerprint"]
    )


def test_a_moved_weight_moves_the_fingerprint(config):
    before = config.run_snapshot()["config_fingerprint"]

    config.tech_weights["blockchain"] = 3.0
    after = config.run_snapshot()["config_fingerprint"]

    assert before != after


def test_the_fingerprint_ignores_a_field_already_in_the_payload():
    """So the digest of an archived block is the one stored in it, not a rehash."""
    from academic_hunter.core.infra.config import config_fingerprint

    payload = {"settings": {"start_year": 2021}}

    assert config_fingerprint(payload) == config_fingerprint(
        {**payload, "config_fingerprint": "sha256:whatever"}
    )


def test_the_fingerprint_does_not_depend_on_key_order():
    from academic_hunter.core.infra.config import config_fingerprint

    assert config_fingerprint({"a": 1, "b": 2}) == config_fingerprint({"b": 2, "a": 1})
