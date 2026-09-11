"""The run's numbers are read back by other tools, so the file must exist whole.

Measured defect: `run_stats_<ts>.json` was written straight to its final path.
Anything reading it during the write — the writing tools, an article-outline
pass, a watcher — could open a file that exists and is half a document, and get
a JSON parse error from a file that is complete a millisecond later.
"""

import json
from pathlib import Path

import pytest

from academic_hunter.plugins.exporters.base import ExportContext
from academic_hunter.plugins.exporters.prisma import PrismaExporter


def context(output_dir, papers=1):
    return ExportContext(
        papers=[{"Title": f"Paper {i}"} for i in range(papers)],
        stats={
            "identified": {"OpenAlex": 10},
            "duplicates_removed": 2,
            "excluded_score": 1,
            "excluded_year": 0,
            "excluded_anchors": 0,
            "excluded_technical_score": 0,
            "included_final": papers,
            "exclusions_by_source": {},
        },
        settings={"min_relevance_score": 3.5, "start_year": 2021},
        query_history=[],
        anchors={},
        tech_strings={},
        timestamp="test_run",
        output_dir=output_dir,
    )


def stats_file(tmp_path):
    return next(Path(tmp_path).rglob("run_stats_*.json"))


def test_the_stats_file_is_complete_and_parses(tmp_path):
    PrismaExporter().export(context(tmp_path, papers=3))

    payload = json.loads(stats_file(tmp_path).read_text(encoding="utf-8"))

    assert payload["included_final"] == 3
    assert payload["identified"] == {"OpenAlex": 10}


def test_a_failed_write_leaves_the_previous_file_intact(tmp_path, monkeypatch):
    """The property that matters: the file is never a half-written one."""
    exporter = PrismaExporter()
    exporter.export(context(tmp_path, papers=3))
    target = stats_file(tmp_path)
    before = target.read_text(encoding="utf-8")

    def refuse(self, destination):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", refuse)
    with pytest.raises(OSError):
        exporter.export(context(tmp_path, papers=9))

    assert target.read_text(encoding="utf-8") == before
    assert json.loads(target.read_text(encoding="utf-8"))["included_final"] == 3


def test_no_partial_file_survives_a_successful_write(tmp_path):
    PrismaExporter().export(context(tmp_path))

    leftovers = list(Path(tmp_path).rglob("*.part"))

    assert leftovers == [], f"a temp file was left behind: {leftovers}"


def test_the_temp_file_is_a_sibling_of_the_target(tmp_path, monkeypatch):
    """It has to be: `replace` is only atomic within one filesystem."""
    written_from = []
    original_replace = Path.replace

    def record(self, destination):
        written_from.append((self, destination))
        return original_replace(self, destination)

    monkeypatch.setattr(Path, "replace", record)
    PrismaExporter().export(context(tmp_path))

    assert written_from, "the write did not go through a temp file"
    temporary, destination = written_from[0]
    assert temporary.parent == destination.parent, (
        "a temp file in another directory makes the rename a copy"
    )
    assert temporary.name.startswith("run_stats_")
