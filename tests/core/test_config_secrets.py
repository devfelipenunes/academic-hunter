"""Credentials must never be serialised back to a caller.

``read_config`` and the ``config/current`` resource hand the config to the MCP
client, which puts it in the agent's context — and a key that reaches a
conversation log has leaked. The live ``settings`` still has to carry the real
values, because the connectors read them straight from there.
"""

import json

import pytest

from academic_hunter.core.infra.config import REDACTED, HunterConfig

SECRET = "s2k-secret-value"
NESTED_SECRET = "core-nested-secret"

CONFIG = {
    "settings": {
        "start_year": 2021,
        "semantic_scholar_api_key": SECRET,
        "api_keys": {
            "semantic_scholar": SECRET,
            "core": NESTED_SECRET,
            "openalex": "",
        },
    },
    "anchors": {"cat": ["blockchain"]},
    "technical_strings": {},
    "technical_weights": {},
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
