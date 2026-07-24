"""Tests for structured response schemas (Pydantic models).

Validates serialization, default values, and optional-field handling
of ToolResult, ConfigData, SearchResult, and PaperData.
"""

import pytest
from pydantic import ValidationError
from academic_hunter.interfaces.mcp.schemas.responses import (
    ToolResult,
    ConfigData,
    SearchResult,
    PaperData,
)


class TestToolResult:
    def test_success_result(self):
        r = ToolResult(success=True, message="OK")
        assert r.success is True
        assert r.message == "OK"
        assert r.data is None

    def test_failure_result(self):
        r = ToolResult(success=False, message="Error occurred")
        assert r.success is False
        assert r.message == "Error occurred"

    def test_with_data(self):
        r = ToolResult(success=True, message="Done", data={"key": "val"})
        assert r.data == {"key": "val"}

    def test_serializes_to_dict(self):
        r = ToolResult(success=True, message="OK")
        d = r.model_dump()
        assert d["success"] is True
        assert d["message"] == "OK"
        assert d["data"] is None

    def test_success_required(self):
        with pytest.raises(ValidationError):
            ToolResult(message="missing success")


class TestConfigData:
    def test_inherits_tool_result(self):
        r = ConfigData(success=True, message="Config loaded")
        assert isinstance(r, ToolResult)

    def test_default_values(self):
        r = ConfigData(success=True, message="OK")
        assert r.data is None


class TestSearchResult:
    def test_inherits_tool_result(self):
        r = SearchResult(success=True, message="Search done")
        assert isinstance(r, ToolResult)


class TestPaperData:
    def test_minimal_paper(self):
        p = PaperData(doi="10.1234/test", title="Test Paper")
        assert p.doi == "10.1234/test"
        assert p.title == "Test Paper"

    def test_all_fields(self):
        p = PaperData(
            doi="10.1234/test",
            title="Test Paper",
            abstract="An abstract here",
            year=2024,
            source="arXiv",
            url="https://arxiv.org/abs/1234",
            venue="Conference X",
            semantic_relevance=0.95,
            score=85.0,
        )
        assert p.abstract == "An abstract here"
        assert p.year == 2024
        assert p.source == "arXiv"

    def test_optional_fields_default_to_none(self):
        p = PaperData(doi="10.1234/test", title="Test Paper")
        assert p.abstract is None
        assert p.year is None
        assert p.source is None
        assert p.url is None
        assert p.venue is None
        assert p.semantic_relevance is None
        assert p.score is None

    def test_doi_required(self):
        with pytest.raises(ValidationError):
            PaperData(title="Missing DOI")

    def test_title_required(self):
        with pytest.raises(ValidationError):
            PaperData(doi="10.1234/test")

    def test_serializes_to_dict(self):
        p = PaperData(doi="10.1234/x", title="T")
        d = p.model_dump()
        assert d["doi"] == "10.1234/x"
        assert d["title"] == "T"
