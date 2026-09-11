"""A connector must be counted under the name it stamps on its papers.

Measured defect: Semantic Scholar was registered as "Semantic Scholar" and
stamped `Source: "SemanticScholar"`. The run then reported that source with a
count and a second source with a zero, in the PRISMA table and in the CSV.
"""

import pytest

from academic_hunter.plugins.connectors import CONNECTORS, _CONNECTOR_NAMES, _register
from academic_hunter.plugins.connectors.base import BaseConnector


def test_every_connector_declares_a_source_name():
    for name, cls in CONNECTORS.items():
        assert cls.SOURCE_NAME, f"{name} declares no SOURCE_NAME"


def test_the_registry_key_is_what_the_connector_stamps():
    mismatched = {
        name: cls.SOURCE_NAME for name, cls in CONNECTORS.items() if cls.SOURCE_NAME != name
    }
    assert not mismatched, f"registered under one name, stamps another: {mismatched}"


def test_registering_a_connector_that_stamps_another_name_fails():
    """The failure mode is silent, so registration is where it has to be loud."""

    class Liar(BaseConnector):
        SOURCE_NAME = "Something Else"

    with pytest.raises(ValueError, match="Something Else"):
        _register("crossref", Liar)


def test_registering_an_unknown_module_is_ignored():
    class Anonymous(BaseConnector):
        SOURCE_NAME = "Whoever"

    _register("not_a_connector_module", Anonymous)

    assert "Whoever" not in CONNECTORS
    assert _CONNECTOR_NAMES.get("not_a_connector_module") is None
