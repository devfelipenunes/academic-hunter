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
        "   uses. It returns those terms, counted, and no configuration: you\n"
        "   write the anchors and technical terms yourself.\n"
        "2. Use `update_config` with the terms you wrote, adding any the field\n"
        "   uses that the discovery could not see. Read what it reports the\n"
        "   configuration will fail to do before moving on.\n"
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
        f"1. Use `quick_topic_discovery('{topic}')` to find the terms this\n"
        "   field's titles use. It returns no configuration, so you write the\n"
        "   anchors and technical terms from those terms.\n"
        "2. Use `update_config` to apply what you wrote\n"
        "3. Use `run_search` to execute the pipeline\n"
        "4. Use `semantic_search` to find similar work in the indexed corpus\n"
        "5. Export the findings to Obsidian\n"
    )
