"""Tests for MCP prompt templates.

Verifies that:
- ``systematic_review`` returns a valid template with topic and question.
- ``quick_discovery`` returns a valid template with topic.
- Templates contain the expected workflow steps, in the order that works.
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


async def test_systematic_review_discovers_before_it_configures():
    """The jargon has to be found before the config that needs it is written.

    Presence was all this file used to check, and an inverted prompt passed it:
    ``update_config`` was step 1 and ``quick_topic_discovery`` step 2. An agent
    following that configures a search before knowing what to search for, and
    has no reason to come back to the discovery step afterwards.
    """
    result = await systematic_review("AI", "AI question")

    assert result.index("quick_topic_discovery") < result.index("update_config")
    assert result.index("update_config") < result.index("run_search")
    assert result.index("run_search") < result.index("read_latest_report")


async def test_quick_discovery_template():
    """Returns a template with topic embedded."""
    result = await quick_discovery("Quantum Computing")
    assert "Quantum Computing" in result


async def test_quick_discovery_searches_before_it_reads_the_corpus():
    """``semantic_search`` needs an indexed corpus, so the search comes first.

    This prompt used to run discovery -> ``semantic_search`` -> Obsidian without
    naming ``update_config`` or ``run_search`` at all. On a cold server
    ``semantic_search`` answers "Vector store not available. Run a search
    first" — a step that cannot work, in a prompt that never mentioned the step
    that would make it work.
    """
    result = await quick_discovery("Blockchain")

    assert result.index("quick_topic_discovery") < result.index("update_config")
    assert result.index("update_config") < result.index("run_search")
    assert result.index("run_search") < result.index("semantic_search")


async def test_quick_discovery_contains_steps():
    """Template includes the exploration steps."""
    result = await quick_discovery("Blockchain")
    assert "quick_topic_discovery" in result
    assert "semantic_search" in result
    assert "Export the findings" in result or "Obsidian" in result
