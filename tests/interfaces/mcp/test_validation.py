"""Tests for input validation module."""

import pytest
from academic_hunter.interfaces.mcp.validation import (
    validate_doi,
    validate_query,
    validate_limit,
    validate_topic,
    validate_email,
    validate_orcid,
)


class TestValidateDOI:
    def test_valid_doi(self):
        assert validate_doi("10.1234/test") == "10.1234/test"

    def test_valid_doi_with_slash(self):
        assert validate_doi("10.1000/abc123") == "10.1000/abc123"

    def test_empty_doi(self):
        with pytest.raises(ValueError, match="DOI is required"):
            validate_doi("")

    def test_whitespace_doi(self):
        with pytest.raises(ValueError, match="DOI is required"):
            validate_doi("   ")

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Invalid DOI format"):
            validate_doi("not-a-doi")

    def test_strips_whitespace(self):
        assert validate_doi("  10.1234/test  ") == "10.1234/test"


class TestValidateQuery:
    def test_valid_query(self):
        assert validate_query("CBDC") == "CBDC"

    def test_empty_query(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_query("")

    def test_custom_field_name(self):
        with pytest.raises(ValueError, match="topic cannot be empty"):
            validate_query("", field="topic")


class TestValidateLimit:
    def test_valid_limit(self):
        assert validate_limit(10) == 10

    def test_none_returns_default(self):
        assert validate_limit(None) == 10
        assert validate_limit(None, default=50) == 50

    def test_clamps_to_max(self):
        assert validate_limit(1000, max_limit=50) == 50

    def test_negative_returns_default(self):
        assert validate_limit(-1) == 10

    def test_zero_returns_default(self):
        assert validate_limit(0) == 10


class TestValidateTopic:
    def test_valid_topic(self):
        assert validate_topic("CBDC") == "CBDC"

    def test_empty_topic(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_topic("")


class TestValidateEmail:
    def test_valid_email(self):
        assert validate_email("user@example.com") == "user@example.com"

    def test_empty_returns_empty(self):
        assert validate_email("") == ""

    def test_invalid_email(self):
        with pytest.raises(ValueError, match="Invalid email"):
            validate_email("not-an-email")


class TestValidateORCID:
    def test_valid_orcid(self):
        assert validate_orcid("0000-0002-1825-0097") == "0000-0002-1825-0097"

    def test_empty_orcid(self):
        with pytest.raises(ValueError, match="ORCID iD is required"):
            validate_orcid("")

    def test_invalid_orcid_format(self):
        with pytest.raises(ValueError, match="Invalid ORCID format"):
            validate_orcid("1234-5678")
