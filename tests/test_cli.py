"""Tests for the CLI entry points (interactive wizard removed)."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_stopwords_available_in_utils():
    """_STOPWORDS is defined in _utils."""
    from academic_hunter.interfaces.mcp.tools._utils import _STOPWORDS
    assert len(_STOPWORDS) > 10
    assert "the" in _STOPWORDS


def test_modes_are_three():
    """MODES contains exactly 3 entries."""
    from academic_hunter.cli import MODES
    assert len(MODES) == 3
    assert {m[0] for m in MODES} == {"keyword", "embedding", "hybrid"}


def test_main_defaults_to_run():
    """main() dispatches to run_scraper when no command given."""
    from academic_hunter.cli import main
    with patch("sys.argv", ["academic-hunter"]), \
         patch("academic_hunter.cli.run_scraper") as m_run:
        main()
        m_run.assert_called_once()


def test_main_run_command():
    """main() dispatches to run_scraper with 'run' command."""
    from academic_hunter.cli import main
    with patch("sys.argv", ["academic-hunter", "run"]), \
         patch("academic_hunter.cli.run_scraper") as m_run:
        main()
        m_run.assert_called_once()


def test_main_benchmark_command():
    """main() dispatches to run_benchmark with 'benchmark' command."""
    from academic_hunter.cli import main
    with patch("sys.argv", ["academic-hunter", "benchmark"]), \
         patch("academic_hunter.cli.run_benchmark") as m_bench:
        main()
        m_bench.assert_called_once()


def test_main_benchmark_with_limit():
    """main() passes --limit to run_benchmark."""
    from academic_hunter.cli import main
    with patch("sys.argv", ["academic-hunter", "benchmark", "--limit", "50"]), \
         patch("academic_hunter.cli.run_benchmark") as m_bench:
        main()
        m_bench.assert_called_once_with(50)


def test_no_interactive_command():
    """'interactive' subcommand no longer exists."""
    from academic_hunter.cli import main
    with patch("sys.argv", ["academic-hunter", "interactive"]), \
         pytest.raises(SystemExit):
        main()


def test_run_scraper_executes_hunter():
    """run_scraper creates AcademicHunter and runs the pipeline."""
    from academic_hunter.cli import run_scraper
    mock_hunter = MagicMock()
    mock_config = MagicMock()
    mock_config.settings = {"limit_per_query": 50}
    with patch("sys.argv", ["academic-hunter"]), \
         patch("academic_hunter.cli.AcademicHunter") as m_hunter, \
         patch.object(Path, "write_text"):
        m_hunter.return_value = mock_hunter
        mock_hunter.config = mock_config
        run_scraper()
        mock_hunter.run.assert_called_once()


def test_run_scraper_with_limit():
    """run_scraper passes --limit to hunter.run()."""
    from academic_hunter.cli import run_scraper
    mock_hunter = MagicMock()
    with patch("sys.argv", ["academic-hunter", "--limit", "25"]), \
         patch("academic_hunter.cli.AcademicHunter") as m_hunter, \
         patch.object(Path, "write_text"):
        m_hunter.return_value = mock_hunter
        run_scraper()
        mock_hunter.run.assert_called_once_with(limit_per_source=25)


def test_run_scraper_benchmark_flag():
    """run_scraper with --benchmark delegates to run_benchmark."""
    from academic_hunter.cli import run_scraper
    with patch("sys.argv", ["academic-hunter", "--benchmark"]), \
         patch("academic_hunter.cli.run_benchmark") as m_bench:
        run_scraper()
        m_bench.assert_called_once()


def test_run_benchmark_all_modes():
    """run_benchmark executes all 3 scoring modes."""
    from academic_hunter.cli import run_benchmark
    mock_stats = {
        "identified": {"ArXiv": 10, "Crossref": 5},
        "excluded_year": 2, "excluded_anchors": 1,
        "excluded_technical_score": 3, "included_final": 7,
    }
    with patch("academic_hunter.cli.AcademicHunter") as m_hunter, \
         patch("academic_hunter.cli.HunterConfig") as m_config, \
         patch("academic_hunter.cli.Path.write_text") as m_write, \
         patch("builtins.print"):
        mock_config = MagicMock()
        mock_config.settings = {"limit_per_query": 100}
        m_config.return_value = mock_config
        mock_hunter = MagicMock()
        mock_hunter.stats = mock_stats
        mock_hunter.consolidated_results = {"p1": {"Relevance_Score": 9.5}}
        m_hunter.return_value = mock_hunter
        run_benchmark()
        assert m_config.call_count >= 3
        assert m_hunter.call_count >= 3
        m_write.assert_called_once()


def test_run_benchmark_saves_results():
    """run_benchmark saves results to benchmark_results.json."""
    from academic_hunter.cli import run_benchmark
    with patch("academic_hunter.cli.AcademicHunter") as m_hunter, \
         patch("academic_hunter.cli.HunterConfig") as m_config, \
         patch("academic_hunter.cli.Path") as m_path, \
         patch("builtins.print"):
        mock_config = MagicMock()
        mock_config.settings = {"limit_per_query": 100}
        m_config.return_value = mock_config
        mock_hunter = MagicMock()
        mock_hunter.stats = {"identified": {}, "excluded_year": 0, "excluded_anchors": 0,
                             "excluded_technical_score": 0, "included_final": 0}
        mock_hunter.consolidated_results = {"p1": {"Relevance_Score": 9.5}}
        m_hunter.return_value = mock_hunter
        run_benchmark()
        m_path.assert_any_call("results")
