"""Tests for MCP prompt templates.

Verifies that:
- ``systematic_review`` returns a valid template with topic and question.
- ``quick_discovery`` returns a valid template with topic.
- Templates contain the expected workflow steps.
"""

from academic_hunter.interfaces.mcp.prompts import systematic_review, quick_discovery


async def test_systematic_review_template():
    """Returns a template with topic and research question embedded."""
    result = await systematic_review("CBDC", "How do CBDCs affect monetary policy?")
    assert "CBDC" in result
    assert "How do CBDCs affect monetary policy?" in result
    assert "systematic review" in result.lower()


async def test_systematic_review_contains_steps():
    """Template includes the expected workflow steps."""
    result = await systematic_review("AI", "AI question")
    assert "update_config" in result
    assert "quick_topic_discovery" in result
    assert "run_search" in result
    assert "read_latest_report" in result
    assert "export_to_obsidian" in result


async def test_quick_discovery_template():
    """Returns a template with topic embedded."""
    result = await quick_discovery("Quantum Computing")
    assert "Quantum Computing" in result


async def test_quick_discovery_contains_steps():
    """Template includes the exploration steps."""
    result = await quick_discovery("Blockchain")
    assert "quick_topic_discovery" in result
    assert "semantic_search" in result
    assert "Export the findings" in result or "Obsidian" in result
