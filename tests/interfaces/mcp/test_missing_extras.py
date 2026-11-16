"""A tool that cannot run without an extra has to name the extra.

The tools that need the `ml` stack do not fail loudly on a base install — they
answer, and the answer is what the agent reads. Telling it "sklearn" or
"BERTopic" is not something a reader can act on without already knowing this
project's packaging; naming the extra is.

Matched as text, like `tests/test_install_instructions.py`: it stops the
wording from going back, and would not catch a message that names the extra in
fresh words. The behavioural tests beside each tool are what cover the paths.
"""

from pathlib import Path

TOOLS = Path(__file__).resolve().parents[3] / "src" / "academic_hunter" / "interfaces" / "mcp" / "tools"

NEEDS_ML = ("clustering", "dedup", "novelty", "summarize", "visualization")


def test_every_tool_that_needs_the_ml_stack_names_the_extra():
    """`find_novel_papers` was the one that answered ``Required library not
    installed: No sklearn`` — the library, which is not the thing to install."""
    missing = [
        name
        for name in NEEDS_ML
        if "academic-hunter[ml]" not in (TOOLS / f"{name}.py").read_text(encoding="utf-8")
    ]

    assert not missing, f"these never name the extra they need: {missing}"


def test_the_list_of_ml_tools_is_not_stale():
    """A new tool importing the ML stack without naming the extra is the next one.

    The check above only knows the names written in it, so it goes on passing
    when a sixth tool is added. This one looks for the imports instead.
    """
    markers = ("bertopic", "sklearn", "hdbscan", "umap", "sentence_transformers")

    importing = {
        path.stem
        for path in TOOLS.glob("*.py")
        if not path.name.startswith("_")
        and any(marker in path.read_text(encoding="utf-8") for marker in markers)
    }

    assert importing <= set(NEEDS_ML), (
        f"these import the ML stack and are not checked above: {sorted(importing - set(NEEDS_ML))}"
    )
