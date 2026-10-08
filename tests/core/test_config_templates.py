"""The shipped template is the only description of the format a user gets.

``install.py`` copies ``config.example.json`` over the user's ``config.json``, and
``paths`` falls back to ``config.default.json`` inside the package. Both were
written before ``keyword_only_terms`` and ``keyword_only_category`` were wired to
the keyword-only connectors, so neither mentioned them: the terms that stand in
for a topic configured with no anchors were reachable only by guessing the name.

The other direction is pinned too. ``blocked_sources`` sits on the config and is
exposed by ``read_config``, which makes it look like a setting — but it is run
state, filled by a 429 and cleared at the top of every run. Persisting it would
turn a transient throttle into a permanent exclusion.
"""

import json
import shutil
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from academic_hunter.core.infra import SearchState
from academic_hunter.core.infra.config import HunterConfig
from academic_hunter.core.pipeline.enricher import MetadataEnricher
from academic_hunter.core.pipeline.steps import RecomputeRanksStep

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = (
    REPO_ROOT / "config.example.json",
    REPO_ROOT / "src" / "academic_hunter" / "core" / "infra" / "config.default.json",
)


@pytest.fixture(params=TEMPLATES, ids=lambda p: p.name)
def template(tmp_path, request):
    """A private copy — ``save()`` redirects a config found inside the package."""
    copy = tmp_path / request.param.name
    shutil.copy(request.param, copy)
    return copy


def test_a_template_mentions_every_key_a_save_writes(template):
    before = set(json.loads(template.read_text(encoding="utf-8")))

    HunterConfig(config_path=str(template)).save()
    after = set(json.loads(template.read_text(encoding="utf-8")))

    assert after <= before, (
        f"{template.name} does not mention {sorted(after - before)}, which save() "
        "writes: anyone reading the template to learn the format cannot find them"
    )


def test_the_packaged_default_carries_the_keyword_only_keys():
    data = json.loads(TEMPLATES[1].read_text(encoding="utf-8"))
    assert data["keyword_only_terms"] == []
    assert data["keyword_only_category"] == ""


def test_the_example_shows_the_shape_a_keyword_only_topic_needs():
    data = json.loads(TEMPLATES[0].read_text(encoding="utf-8"))
    assert isinstance(data["keyword_only_terms"], list)
    assert isinstance(data["keyword_only_category"], str)


def test_a_source_blocked_mid_run_never_reaches_the_file(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"settings": {"user_email": "a@b.c"}}), encoding="utf-8")
    config = HunterConfig(config_path=str(path))

    config.blocked_sources.add("api.openalex.org")
    config.save()

    assert "blocked_sources" not in json.loads(path.read_text(encoding="utf-8"))


def _settings_of(template, **overrides):
    settings = json.loads(template.read_text(encoding="utf-8"))["settings"]
    return {**settings, "min_relevance_score": 0.0, **overrides}


def _weights_applied(template, ranking_query=""):
    """The weights the shipped rank step applies — read from a run, not recomputed.

    Reimplementing the step's query-mode forcing here would let this test and the
    step drift apart, and the drift is precisely what it exists to catch.
    """
    papers = {
        "a": {"Title": "alpha self-sovereign", "Abstract": "identity", "_kw_score": 9.0, "_sem_score": 0.9},
        "b": {"Title": "beta ledger", "Abstract": "ledger", "_kw_score": 1.0, "_sem_score": 0.1},
    }
    hunter = MagicMock()
    hunter.settings = _settings_of(template, ranking_query=ranking_query)
    hunter.lock = threading.RLock()
    hunter.state.stats = {}
    hunter.semantic_screener = None
    hunter.config.screener_config.return_value = {}
    hunter.config.min_inclusion_score.return_value = 0.0
    hunter.scorer.calculate_score.return_value = 0.0
    hunter.consolidated_results = papers

    RecomputeRanksStep(hunter).run()

    return hunter.state.stats["fusion"]["weights"]


def test_neither_template_names_fusion_weights():
    """The key's presence is not neutral, so neither shipped template may carry it.

    With ``ranking_query`` empty, absent and ``{"keyword": 0.7, "embedding":
    0.3}`` score the same. With a query set they do not: absent lets the step
    force 1.0/0.0, and an explicit key overrides that forcing. The shipped
    example carried the key, so a user who added a query to it silently bought a
    different behavior from a user of the packaged default — the same corpus,
    two orderings, nothing saying which rule was in force.
    """
    for template in TEMPLATES:
        settings = json.loads(template.read_text(encoding="utf-8"))["settings"]
        assert "fusion_weights" not in settings, (
            f"{template.name} names fusion_weights; the code default has to govern "
            "it, or the two templates disagree as soon as a query is configured"
        )


def test_both_templates_apply_the_same_weights_in_both_query_modes():
    """The two templates have to be interchangeable, and the modes differ.

    With no query the code default governs — 0.7/0.3. With a query the step
    forces 1.0/0.0, which is the behaviour a user gets by adding a query to the
    shipped example. Both templates must land on the same side of that.
    """
    expected = {
        "": {"keyword": 0.7, "embedding": 0.3, "citation": 0.0},
        "self-sovereign identity": {"keyword": 1.0, "embedding": 0.0, "citation": 0.0},
    }
    for query, weights_expected in expected.items():
        weights = [_weights_applied(template, query) for template in TEMPLATES]
        assert weights[0] == weights[1] == weights_expected, (
            f"the templates disagree on the weights they apply with ranking_query={query!r}"
        )


def test_nothing_the_packaged_default_carries_is_missing_from_the_example():
    """The example is what a user copies, so it has to cover the packaged default.

    The key sets are not equal and should not be: the example also documents the
    keys whose defaults already say what the example says, which the next two
    tests pin. What must not happen is the default growing a setting the example
    never mentions.
    """
    example = json.loads(TEMPLATES[0].read_text(encoding="utf-8"))["settings"]
    default = json.loads(TEMPLATES[1].read_text(encoding="utf-8"))["settings"]

    assert set(default) <= set(example), (
        f"config.example.json does not mention {sorted(set(default) - set(example))}, "
        "which the packaged default carries"
    )


def test_a_configured_citation_backfill_behaves_as_the_absent_key_does():
    """The key is kept in the example only because its value is the default one.

    Otherwise the example would teach a behaviour the packaged default does not
    have. Asserted by running the backfill twice over the same paper — once with
    the example's block, once with the default's silence — and comparing the
    answer, not by restating the literal the source already contains.
    """
    class _Connector:
        def fetch_citations_by_dois(self, dois, chunk_size=50):
            return {"10.1/a": 12}

    def backfill(settings):
        paper = {"Title": "A", "DOI": "10.1/a", "Citations": 0,
                 "Citations_Source": "none", "_kw_score": 4.0}
        state = SearchState()
        state.consolidated_results = {"slug-1": paper}
        enricher = MetadataEnricher(
            connectors={"openalex": _Connector()},
            state=state,
            lock=threading.RLock(),
            settings={"citations_backfill": settings} if settings else {},
        )
        summary = enricher.backfill_citations()
        return summary, paper["Citations"], paper["_kw_score"]

    example = json.loads(TEMPLATES[0].read_text(encoding="utf-8"))["settings"]["citations_backfill"]

    assert example["enabled"] is True and example["invalidate_scores"] is True, (
        "the example states a value the code does not default to; that is not inert"
    )
    assert backfill(example) == backfill(None)


def test_a_configured_impact_percentile_bands_the_corpus_as_the_absent_key_does():
    """Same rule as the backfill above: the example states a value, the code has it.

    A different example value would silently move the cutoff every sidecar
    records, and the cutoff is what ``papers_above`` counts.
    """
    example = _settings_of(TEMPLATES[0])
    default = _settings_of(TEMPLATES[1])

    assert "impact_percentile" in example
    assert "impact_percentile" not in default
    assert _band(example) == _band(default)


def _band(settings):
    """The impact block the rank step writes, for a settings dict."""
    papers = {
        f"p{i}": {"Title": f"P{i}", "Citations": count, "_kw_score": 5.0}
        for i, count in enumerate([0, 0, 3, 20, 120])
    }
    hunter = MagicMock()
    hunter.settings = dict(settings)
    hunter.lock = threading.RLock()
    hunter.state.stats = {}
    hunter.semantic_screener = None
    hunter.config.screener_config.return_value = {}
    hunter.config.min_inclusion_score.return_value = 0.0
    hunter.scorer.calculate_score.return_value = 0.0
    hunter.consolidated_results = papers

    RecomputeRanksStep(hunter).run()

    return hunter.state.stats["impact"]
