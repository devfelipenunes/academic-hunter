"""Which connectors can run, and what they say when they cannot.

A source that needs a credential and does not have one used to be called
anyway. Measured on a full run: Semantic Scholar took three 429s, was blocked
mid-run, and the reply reported ``Semantic Scholar: 0`` -- which reads exactly
like a source that was asked and found nothing.
"""

import threading

import pytest

from academic_hunter.plugins.connectors.base import BaseConnector
from academic_hunter.plugins.connectors.core_ac import CoreConnector
from academic_hunter.plugins.connectors.semanticscholar import SemanticScholarConnector

KEY = "s2-test-key-do-not-use"


def test_a_connector_with_no_requirement_is_available():
    """The default has to be "runs": a connector that forgot to answer for
    itself must not be silently dropped from every run."""

    class _Plain(BaseConnector):
        SOURCE_NAME = "Plain"

    assert _Plain.unavailable_reason({}) == ""


def test_semantic_scholar_reports_the_missing_key():
    assert SemanticScholarConnector.unavailable_reason({}) != ""


def test_the_reason_names_where_to_configure_it():
    """A reason that says only "no API key" leaves the reader with a problem and
    no move. Both places the key is read from have to be named."""
    reason = SemanticScholarConnector.unavailable_reason({})

    assert "SEMANTIC_SCHOLAR_API_KEY" in reason
    assert "settings.api_keys.semantic_scholar" in reason


@pytest.mark.parametrize(
    "settings",
    [
        {"semantic_scholar_api_key": KEY},
        {"api_keys": {"semantic_scholar": KEY}},
    ],
)
def test_semantic_scholar_runs_once_a_key_is_configured(settings):
    """The gate has to open, or "does not run without a key" is indistinguishable
    from "never runs"."""
    assert SemanticScholarConnector.unavailable_reason(settings) == ""


def test_the_environment_variable_opens_the_gate_too(monkeypatch):
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", KEY)

    assert SemanticScholarConnector.unavailable_reason({}) == ""


def test_a_whitespace_key_does_not_count(monkeypatch):
    """An empty string is what the config ships with, and it must read as absent
    rather than as a credential."""
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "")

    assert SemanticScholarConnector.unavailable_reason({}) != ""


class TestCore:
    """CORE's search endpoint answers 401 without a key, and the run said ``0``.

    Which is the number a source that was asked and found nothing also produces,
    so an unconfigured source has been reporting itself as a consulted one on
    every run -- and every PRISMA diagram has carried it as a source that
    contributed nothing rather than as a source that was never asked.
    """

    def test_core_reports_the_missing_key(self, monkeypatch):
        monkeypatch.delenv("CORE_API_KEY", raising=False)

        assert CoreConnector.unavailable_reason({}) != ""

    def test_the_reason_names_where_to_configure_it(self, monkeypatch):
        monkeypatch.delenv("CORE_API_KEY", raising=False)
        reason = CoreConnector.unavailable_reason({})

        assert "CORE_API_KEY" in reason
        assert "settings.api_keys.core" in reason

    @pytest.mark.parametrize(
        "settings",
        [
            {"core_api_key": KEY},
            {"api_keys": {"core": KEY}},
        ],
    )
    def test_core_runs_once_a_key_is_configured(self, settings, monkeypatch):
        monkeypatch.delenv("CORE_API_KEY", raising=False)

        assert CoreConnector.unavailable_reason(settings) == ""

    def test_the_environment_variable_opens_the_gate_too(self, monkeypatch):
        monkeypatch.setenv("CORE_API_KEY", KEY)

        assert CoreConnector.unavailable_reason({}) == ""

    def test_the_key_the_headers_send_is_the_key_the_gate_reads(self, monkeypatch):
        """Two lookups of the same credential is how one of them goes stale."""
        monkeypatch.delenv("CORE_API_KEY", raising=False)
        settings = {"api_keys": {"core": KEY}}

        connector = CoreConnector(
            cache=None, settings=settings, query_history=[],
            lock=threading.RLock(), semaphore=threading.Semaphore(1), use_cache=False,
        )

        assert connector.get_headers()["ApiKey"] == KEY
        assert CoreConnector.unavailable_reason(settings) == ""
