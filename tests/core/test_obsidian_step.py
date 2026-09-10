"""Contract tests for the Obsidian auto-export pipeline step.

The step used to import ``export_to_obsidian`` straight from the MCP tool layer
— the domain reaching outwards into the interface layer. It now calls
``hunter.obsidian_export``, supplied by the composition root, so these tests pin
both the call shape and the no-op paths.
"""

from unittest.mock import MagicMock

from academic_hunter.core.pipeline.steps import AutoExportObsidianStep


def _hunter(obsidian_path="", export=None, papers=None):
    hunter = MagicMock()
    hunter.config.settings = (
        {"obsidian_vault_path": obsidian_path} if obsidian_path else {}
    )
    hunter.anchors = {"cat": ["blockchain"]}
    hunter.connectors = {"ArXiv": object()}
    if export is None:
        # A MagicMock attribute is callable, so an unset export would look
        # configured. Use None to represent "no adapter injected".
        hunter.obsidian_export = None
    else:
        hunter.obsidian_export = export
    hunter.consolidated_results = {
        f"p{i}": {
            "Title": f"Paper {i}",
            "Relevance_Score": 9.0 - i,
            "Year": "2024",
            "Source": "ArXiv",
            "DOI": f"10.0/{i}",
            "URL": f"http://example.com/{i}",
        }
        for i in range(3)
    }
    if papers is not None:
        hunter.consolidated_results = papers
    return hunter


def test_calls_injected_exporter_with_vault_path():
    """The write goes through the injected callable, vault path included."""
    export = MagicMock(return_value="✅ done")
    step = AutoExportObsidianStep(_hunter(obsidian_path="/vault", export=export), "T1")

    step.run()

    assert export.call_count == 1
    kwargs = export.call_args.kwargs
    assert kwargs["vault_path"] == "/vault"
    assert kwargs["topic"] == "Academic Hunter Report T1"
    assert kwargs["tags"] == ["academic-hunter", "research", "automated"]
    assert "Paper 0" in kwargs["content"]


def test_skips_when_vault_not_configured():
    """No configured vault means no export at all."""
    export = MagicMock()
    step = AutoExportObsidianStep(_hunter(obsidian_path="", export=export), "T1")

    step.run()

    export.assert_not_called()


def test_skips_when_no_exporter_injected():
    """A vault without an injected adapter is a no-op, not a crash."""
    step = AutoExportObsidianStep(_hunter(obsidian_path="/vault"), "T1")

    step.run()  # must not raise


def test_skips_when_there_are_no_papers():
    """An empty collection is nothing to report."""
    export = MagicMock()
    step = AutoExportObsidianStep(
        _hunter(obsidian_path="/vault", export=export, papers={}), "T1"
    )

    step.run()

    export.assert_not_called()


def test_exporter_failure_does_not_break_the_run():
    """Export is best-effort: a raising adapter is logged, not propagated."""
    export = MagicMock(side_effect=Exception("vault on fire"))
    step = AutoExportObsidianStep(_hunter(obsidian_path="/vault", export=export), "T1")

    step.run()  # must not raise

    export.assert_called_once()
