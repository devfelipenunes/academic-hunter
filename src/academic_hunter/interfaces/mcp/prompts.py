"""MCP prompt templates — reusable workflows for LLM agents."""


async def systematic_review(topic: str, research_question: str) -> str:
    """Template for a full systematic literature review workflow."""
    return (
        "You are a systematic review assistant.\n"
        f"Topic: {topic}\n"
        f"Research Question: {research_question}\n"
        "\n"
        "Follow these steps in order. Step 2 needs what step 1 finds, so do not\n"
        "skip ahead:\n"
        "1. Run `quick_topic_discovery` to learn the jargon this field actually\n"
        "   uses. It returns the concepts to search for, plus a draft config.\n"
        "2. Use `update_config` with that draft, adding any anchors or technical\n"
        "   terms you know the field uses and the discovery could not see.\n"
        "3. Use `run_search` to execute the pipeline\n"
        "4. Read the coverage `run_search` reports. A source listed as not\n"
        "   queried was never asked: the config is missing something. Fix it with\n"
        "   `update_config` and run the search again.\n"
        "5. Read the report with `read_latest_report`\n"
        "6. Export findings to Obsidian with `export_to_obsidian`\n"
    )


async def quick_discovery(topic: str) -> str:
    """Template for a quick topic exploration."""
    return (
        f"Explore '{topic}' using Academic Hunter:\n"
        f"1. Use `quick_topic_discovery('{topic}')` to find papers and get a\n"
        "   draft config\n"
        "2. Use `update_config` to apply it\n"
        "3. Use `run_search` to execute the pipeline\n"
        "4. Use `semantic_search` to find similar work in the indexed corpus\n"
        "5. Export the findings to Obsidian\n"
    )
