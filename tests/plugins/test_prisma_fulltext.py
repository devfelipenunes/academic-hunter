"""The PRISMA report must not call an already-indexed paper "not obtained".

SLR methodology reads this section to say how many full texts were not
obtained. A paper whose text the index already held was obtained — by an earlier
run — so listing it under "not obtained" understates the coverage.
"""

from pathlib import Path

import pytest

from academic_hunter.plugins.exporters.base import ExportContext
from academic_hunter.plugins.exporters.prisma import PrismaExporter


def report(tmp_path, full_text):
    context = ExportContext(
        papers=[{"Title": "Paper"}],
        stats={
            "identified": {"OpenAlex": 1},
            "duplicates_removed": 0,
            "excluded_year": 0,
            "excluded_anchors": 0,
            "excluded_technical_score": 0,
            "included_final": 1,
            "full_text": full_text,
            "exclusions_by_source": {},
        },
        settings={"min_relevance_score": 3.5, "start_year": 2021},
        query_history=[],
        anchors={},
        tech_strings={},
        timestamp="test_run",
        output_dir=tmp_path,
    )
    PrismaExporter().export(context)
    return next(Path(tmp_path).rglob("FLUXO_PRISMA_*.md")).read_text(encoding="utf-8")


def test_already_indexed_is_reported_as_its_own_line(tmp_path):
    content = report(
        tmp_path,
        {"obtained": 1, "already_indexed": 5, "no_open_access": 2},
    )

    assert "**Already indexed (not re-fetched):** 5" in content


def test_already_indexed_is_not_listed_as_not_obtained(tmp_path):
    content = report(tmp_path, {"obtained": 0, "already_indexed": 5})

    assert "already_indexed" not in content
    assert "Not obtained" not in content


def test_the_real_failures_are_still_listed(tmp_path):
    content = report(
        tmp_path,
        {"obtained": 1, "already_indexed": 5, "no_open_access": 2, "download_failed": 3},
    )

    assert "**Not obtained — no_open_access:** 2" in content
    assert "**Not obtained — download_failed:** 3" in content


def test_the_section_is_absent_when_the_step_did_not_run(tmp_path):
    content = report(tmp_path, {})

    assert "Full Text Retrieval" not in content


def test_a_zero_count_is_not_printed(tmp_path):
    content = report(tmp_path, {"obtained": 1, "already_indexed": 0, "no_doi": 0})

    assert "Already indexed" not in content
    assert "no_doi" not in content
