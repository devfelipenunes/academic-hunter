"""MCP prompt templates — reusable workflows for LLM agents."""


async def systematic_review(topic: str, research_question: str) -> str:
    """Template for a full systematic literature review workflow."""
    return (
        "You are a systematic review assistant.\n"
        f"Topic: {topic}\n"
        f"Research Question: {research_question}\n"
        "\n"
        "Follow these steps:\n"
        "1. Use `update_config` to configure the search\n"
        "2. Run `quick_topic_discovery` to identify key jargon\n"
        "3. Use `run_search` to execute the pipeline\n"
        "4. Read the report with `read_latest_report`\n"
        "5. Export findings to Obsidian with `export_to_obsidian`\n"
    )


async def quick_discovery(topic: str) -> str:
    """Template for a quick topic exploration."""
    return (
        f"Explore '{topic}' using Academic Hunter:\n"
        f"1. Use `quick_topic_discovery('{topic}')` to find papers\n"
        "2. Use `semantic_search` to find similar work\n"
        "3. Export the findings to Obsidian\n"
    )
