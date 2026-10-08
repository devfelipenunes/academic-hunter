"""The vocabulary that tells a measured zero from an unmeasured one.

Before this, every paper the connectors could not answer for carried
``Citations: 0``, indistinguishable from a paper every source agreed was never
cited. The report showed the same number for both and drew a conclusion about
the corpus from a gap in its data.
"""

import pytest

from academic_hunter.core.models.citations import (
    citation_signal,
    citation_summary,
    citation_tokens,
    impact_cutoff,
)


def test_tokens_survive_the_set_join_merge():
    """``Citations_Source`` is merged with ``strategy_set_join``, so it arrives sorted and comma-separated."""
    assert citation_tokens("openalex, openalex-batch") == {"openalex", "openalex-batch"}
    assert citation_tokens("") == set()
    assert citation_tokens(None) == set()


@pytest.mark.parametrize(
    "count,expected",
    [(0, 0.0), (9, 1.0), (75, 1.8808), (1019, 3.0086)],
)
def test_the_signal_is_the_scorer_s_own_transform(count, expected):
    """One definition of citation magnitude in the repository, and zero stays zero."""
    assert citation_signal(count) == pytest.approx(expected, abs=1e-4)


def test_a_bad_count_is_read_as_zero_rather_than_raising():
    assert citation_signal("not a number") == 0.0
    assert citation_signal(None) == 0.0


def test_the_summary_buckets_are_disjoint_and_cover_every_paper():
    papers = [
        {"Citations": 75, "Citations_Source": "openalex-batch"},
        {"Citations": 10, "Citations_Source": "crossref"},
        {"Citations": 0, "Citations_Source": "openalex"},
        {"Citations": 0, "Citations_Source": "unresolved"},
        {"Citations": 0, "Citations_Source": "none"},
        {"Citations": 0},
    ]
    summary = citation_summary(papers)

    assert summary["papers"] == 6
    assert summary["with_count"] == 2
    assert summary["resolved"] == 1
    assert summary["reported"] == 1
    assert summary["confirmed_zero"] == 1
    assert summary["unresolved"] == 1
    assert summary["without_identifier"] == 1
    assert summary["not_asked"] == 1
    assert (
        summary["with_count"]
        + summary["confirmed_zero"]
        + summary["unresolved"]
        + summary["without_identifier"]
        + summary["not_asked"]
    ) == summary["papers"]


def test_the_summary_reads_the_sidecar_s_lowercase_columns():
    """The sidecar writes its own columns in lower case; the same summary describes both."""
    summary = citation_summary([{"citations": 5, "citations_source": "openalex"}])
    assert summary["with_count"] == 1
    assert summary["reported"] == 1


def test_the_impact_band_ignores_the_unmeasured_papers():
    """A corpus that is mostly zeros would otherwise put the line at zero and call every cited paper an outlier."""
    assert impact_cutoff([0, 0, 0, 1, 5, 10, 75, 410], 90) == 75.0
    assert impact_cutoff([0, 0, 0], 90) == 0.0


def test_the_impact_band_follows_the_configured_percentile():
    """The same nearest-rank-lower convention the run's own distribution uses."""
    values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert impact_cutoff(values, 0) == 1.0
    assert impact_cutoff(values, 100) == 10.0
    assert impact_cutoff(values, 50) == 5.0


def test_a_bad_percentile_falls_back_instead_of_raising():
    assert impact_cutoff([1, 2, 3], "not a number") == 2.0
    assert impact_cutoff([1, 2, 3], None) == 2.0
