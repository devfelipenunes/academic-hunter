"""Tests for SearchPipeline (pipeline/manager.py).

Covers methods not exercised by the integration-level pipeline tests:
- _index_results
- _recompute_ranks
- vector_store lazy init
"""

from unittest.mock import MagicMock, PropertyMock, patch


def _make_hunter_with_results(results_dict):
    """Create a mock hunter with consolidated_results as a real dict."""
    hunter = MagicMock()
    hunter.output_dir = MagicMock()
    hunter.output_dir.parent = MagicMock()
    hunter.state.stats = {}
    type(hunter).consolidated_results = PropertyMock(return_value=results_dict)
    return hunter


def test_the_model_is_warmed_before_any_worker_starts():
    """The download has to be serial, and it has to happen before the threads.

    ChromaDB fetches the ONNX model on the first call that embeds, and it tests
    for the file and downloads it without a lock. With one thread per source,
    several raced the same 79 MB into the same paths; measured on a cold cache,
    the two that lost read a model still being written and fell through to zero
    vectors for every paper they scored.
    """
    from academic_hunter.core.pipeline.manager import SearchPipeline

    hunter = MagicMock()
    hunter.settings = {"ablation": {"mode": "hybrid"}}
    warmed = []

    def warm():
        warmed.append(True)
        return True

    hunter.semantic_screener.warm.side_effect = warm

    SearchPipeline(hunter)._warm_semantic_screener()

    assert warmed == [True], "the download was left to the worker threads"


def test_a_refused_warmup_is_remembered_for_the_end_of_the_run():
    """`warm()` is the only place that knows how the load went.

    The flag has to survive the run, because the warning that reports it is
    printed after every worker has finished — long after the screener's own
    state was last written. Discarding the return value meant a run that fell
    back to zero vectors reported its numbers like any other.
    """
    from academic_hunter.core.pipeline.manager import SearchPipeline

    hunter = MagicMock()
    hunter.settings = {"ablation": {"mode": "hybrid"}}
    hunter.semantic_screener.warm.return_value = False

    pipeline = SearchPipeline(hunter)
    pipeline._warm_semantic_screener()

    assert pipeline._semantic_degraded is True


def test_a_warmup_that_succeeds_leaves_the_run_alone():
    from academic_hunter.core.pipeline.manager import SearchPipeline

    hunter = MagicMock()
    hunter.settings = {"ablation": {"mode": "hybrid"}}
    hunter.semantic_screener.warm.return_value = True

    pipeline = SearchPipeline(hunter)
    pipeline._warm_semantic_screener()

    assert pipeline._semantic_degraded is False


def test_a_keyword_only_run_does_not_fetch_the_model():
    """79 MB is a real cost, and a keyword-only run never calls the screener."""
    from academic_hunter.core.pipeline.manager import SearchPipeline

    hunter = MagicMock()
    hunter.settings = {"ablation": {"mode": "keyword"}}

    SearchPipeline(hunter)._warm_semantic_screener()

    hunter.semantic_screener.warm.assert_not_called()


def test_a_hunter_without_a_screener_is_left_alone():
    from academic_hunter.core.pipeline.manager import SearchPipeline

    hunter = MagicMock()
    hunter.settings = {"ablation": {"mode": "hybrid"}}
    hunter.semantic_screener = None

    SearchPipeline(hunter)._warm_semantic_screener()


def test_a_blocked_source_is_unblocked_by_the_next_run():
    """A block lasts for the run that hit the rate limit, not for the session.

    Measured defect: `blocked_sources` lives on the config, which outlives the
    run, and nothing ever cleared it — so one 429 with a long wait silenced that
    source for every run afterwards, in the same process, with no way back
    except restarting.
    """
    from academic_hunter.core.infra.state import SearchState
    from academic_hunter.core.pipeline.manager import SearchPipeline

    hunter = MagicMock()
    hunter.connectors = {"ArXiv": MagicMock(), "OpenAlex": MagicMock()}
    hunter.state = SearchState()
    hunter.blocked_sources = {"api.openalex.org"}

    SearchPipeline(hunter)._reset_run_state()

    assert hunter.blocked_sources == set(), "the source stayed blocked"
    assert set(hunter.state.stats["identified"]) == {"ArXiv", "OpenAlex"}


def test_the_reset_clears_the_block_in_place():
    """It has to be `.clear()`: the connectors hold this very set.

    Rebinding would hand the connectors a new object and leave them reading the
    old one, which is how a reset can look like it worked and change nothing.
    """
    from academic_hunter.core.infra.state import SearchState
    from academic_hunter.core.pipeline.manager import SearchPipeline

    shared = {"api.openalex.org"}
    hunter = MagicMock()
    hunter.connectors = {}
    hunter.state = SearchState()
    hunter.blocked_sources = shared

    SearchPipeline(hunter)._reset_run_state()

    assert shared == set()
    assert hunter.blocked_sources is shared


def test_one_bad_paper_does_not_take_the_page_down_with_it():
    """`stats["identified"]` is incremented before the paper is processed.

    The try used to wrap the fetch *and* the loop over its results, so one paper
    that raised inside `_process_paper` abandoned the rest of the page — and
    those papers had already been counted as identified, so the run reported
    having seen them and shipped none of them.
    """
    from academic_hunter.core.pipeline.manager import SearchPipeline

    hunter = MagicMock()
    hunter.connectors = {"DOAJ": MagicMock(is_keyword_only=False)}
    hunter.tech_strings = {"Infra": ["interoperability"]}
    hunter.anchors = {"Payments": ["Zelle"]}
    hunter.config.keyword_only_category = "Consolidated"
    hunter.config.keyword_only_terms = ["ledger"]

    seen = []

    def process(paper, *args):
        seen.append(paper["Title"])
        if paper["Title"] == "poison":
            raise RuntimeError("a malformed abstract")

    hunter._process_paper.side_effect = process

    def fetch(anchors, tech, limit):
        return [{"Title": "first"}, {"Title": "poison"}, {"Title": "last"}]

    SearchPipeline(hunter)._api_worker("DOAJ", fetch, limit_per_source=5)

    assert seen == ["first", "poison", "last"], "the page was abandoned mid-loop"


def test_the_reset_lowers_the_pacing_that_a_throttled_run_raised():
    """`pacing_delays` is escalated and never lowered, and it outlives the run.

    The connector is built once and reused, so every 429 doubles its delay for
    good: after four throttled runs a 3-second source paces at 48 seconds, in a
    process that stayed up, with nothing reporting why the run got slow. The
    rate limit it was backing off from is long over.
    """
    from academic_hunter.core.infra.state import SearchState
    from academic_hunter.core.pipeline.manager import SearchPipeline

    connector = MagicMock()
    connector.pacing_delays = {"api.openalex.org": 48.0}
    hunter = MagicMock()
    hunter.connectors = {"OpenAlex": connector}
    hunter.state = SearchState()
    hunter.blocked_sources = set()

    SearchPipeline(hunter)._reset_run_state()

    assert connector.pacing_delays == {}, "the escalated delay survived the run"


def _s2_connector(settings):
    """The real connector, so ``setup_pacing`` is the one that ships."""
    import threading

    from academic_hunter.plugins.connectors.semanticscholar import SemanticScholarConnector

    connector = SemanticScholarConnector(
        cache=None,
        settings=settings,
        query_history=[],
        lock=threading.RLock(),
        semaphore=threading.Semaphore(2),
        use_cache=False,
    )
    connector.pacing_delays = {connector.domain: connector.default_delay}
    connector.setup_pacing()
    return connector


def _delay_the_next_request_waits(connector):
    """What ``_make_request`` reads: the dict entry, or the class default."""
    return connector.pacing_delays.get(connector.domain, connector.default_delay)


def _reset(connector):
    from academic_hunter.core.infra.state import SearchState
    from academic_hunter.core.pipeline.manager import SearchPipeline

    hunter = MagicMock()
    hunter.connectors = {connector.SOURCE_NAME: connector}
    hunter.state = SearchState()
    hunter.blocked_sources = set()
    SearchPipeline(hunter)._reset_run_state()


def test_the_reset_keeps_the_pacing_the_key_bought(monkeypatch):
    """The reset emptied the same dict ``setup_pacing`` had written the key into.

    Semantic Scholar paces at 4 s without a key and 1 s with one, and that
    discount is written once, when the hunter is built. Emptying the dict to undo
    the 429 escalation took the discount with it, so the first run of a keyed
    operator fell back to the unkeyed default and every later run stayed there.
    """
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    connector = _s2_connector({"api_keys": {"semantic_scholar": "s2k-test-key"}})
    assert _delay_the_next_request_waits(connector) == 1.0

    _reset(connector)

    assert _delay_the_next_request_waits(connector) == 1.0


def test_the_reset_still_undoes_the_escalation_on_a_keyed_source(monkeypatch):
    """Both have to happen at once: the doubling goes, the discount stays."""
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    connector = _s2_connector({"api_keys": {"semantic_scholar": "s2k-test-key"}})
    connector.pacing_delays[connector.domain] = 16.0

    _reset(connector)

    assert _delay_the_next_request_waits(connector) == 1.0


def test_an_unkeyed_source_resets_to_its_own_default(monkeypatch):
    """The key is what buys the 1 s, so without one the shipped default stands."""
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    connector = _s2_connector({})
    assert _delay_the_next_request_waits(connector) == 4.0

    _reset(connector)

    assert _delay_the_next_request_waits(connector) == 4.0


def test_vector_store_lazy_init():
    """vector_store builds the store once via the injected factory, then caches it.

    The property used to import ``ChromaVectorStore`` itself; it now asks
    ``hunter.vector_store_factory``, which the composition root supplies.
    """
    from academic_hunter.core.pipeline.manager import SearchPipeline

    hunter = MagicMock()
    hunter.output_dir.parent = MagicMock()
    mock_store = MagicMock()
    hunter.vector_store_factory = MagicMock(return_value=mock_store)
    pipeline = SearchPipeline(hunter)
    assert pipeline._vector_store is None

    store = pipeline.vector_store

    assert store == mock_store
    assert pipeline._vector_store == mock_store
    assert pipeline.vector_store == mock_store
    assert hunter.vector_store_factory.call_count == 1


def test_vector_store_lazy_init_failure():
    """vector_store returns None on initialization failure."""
    from academic_hunter.core.pipeline.manager import SearchPipeline

    hunter = MagicMock()
    hunter.output_dir.parent = MagicMock()
    hunter.vector_store_factory = MagicMock(side_effect=Exception("Import failed"))
    pipeline = SearchPipeline(hunter)
    store = pipeline.vector_store

    assert store is None
    assert pipeline._vector_store is None


def test_index_results_no_store():
    """_index_results skips when vector store is None."""
    from academic_hunter.core.pipeline.manager import SearchPipeline

    hunter = MagicMock()
    pipeline = SearchPipeline(hunter)
    pipeline._vector_store = None
    pipeline._index_results()


def test_index_results_no_papers():
    """_index_results skips when no consolidated results."""
    from academic_hunter.core.pipeline.manager import SearchPipeline

    hunter = _make_hunter_with_results({})
    pipeline = SearchPipeline(hunter)
    pipeline._vector_store = MagicMock()
    pipeline._index_results()
    pipeline._vector_store.index_papers.assert_not_called()


def test_index_results_with_papers():
    """_index_results indexes consolidated papers."""
    from academic_hunter.core.pipeline.manager import SearchPipeline

    hunter = _make_hunter_with_results({"p1": {"Title": "Paper"}})
    mock_pipeline = MagicMock()
    mock_vector_store = MagicMock()
    mock_pipeline.vector_store = mock_vector_store
    hunter.pipeline = mock_pipeline

    pipeline = SearchPipeline(hunter)
    pipeline._index_results()
    mock_vector_store.index_papers.assert_called_once_with(
        [{"Title": "Paper"}]
    )


def test_recompute_ranks_no_results():
    """_recompute_ranks skips when no consolidated results."""
    from academic_hunter.core.pipeline.manager import SearchPipeline

    hunter = _make_hunter_with_results({})
    pipeline = SearchPipeline(hunter)
    pipeline._recompute_ranks()


def test_recompute_ranks_single_paper():
    """A single-paper collection still gets a score, at the top of the scale.

    There is no distribution to rank against, but that paper is trivially the
    top of its own collection. It used to be skipped outright, leaving
    Relevance_Score at its 0.0 default — which the downstream threshold filter
    then read as "irrelevant" and dropped, silently emptying any run that
    deduplicated down to one paper.
    """
    from academic_hunter.core.pipeline.manager import SearchPipeline

    hunter = _make_hunter_with_results({"p1": {"Title": "Only paper"}})
    hunter.settings = {"min_relevance_score": 5.0}
    hunter.semantic_screener = None
    hunter.scorer.calculate_score.return_value = 3.0

    pipeline = SearchPipeline(hunter)
    pipeline._recompute_ranks()

    assert hunter.consolidated_results["p1"]["Relevance_Score"] == 10.0


def test_recompute_ranks_two_papers():
    """_recompute_ranks computes geometric mean ranks for 2 papers."""
    from academic_hunter.core.pipeline.manager import SearchPipeline

    results = {
        "p1": {"Title": "Paper 1", "Abstract": "blockchain tech"},
        "p2": {"Title": "Paper 2", "Abstract": "not relevant at all"},
    }
    hunter = _make_hunter_with_results(results)
    hunter.scorer.calculate_score.side_effect = [10.0, 1.0]
    hunter.semantic_screener = None
    hunter.state.stats = {}
    hunter.settings = {"min_relevance_score": 0.0}

    pipeline = SearchPipeline(hunter)
    pipeline._recompute_ranks()

    assert "Relevance_Score" in results["p1"]
    assert "Relevance_Score" in results["p2"]
    assert results["p1"]["Relevance_Score"] >= results["p2"]["Relevance_Score"]


def _hunter_for_a_full_run(connectors, settings=None):
    """A hunter that can survive the whole of `run()` without touching disk.

    The real thread loop is the point of these tests -- it is where the gate
    lives -- so everything expensive that comes after it is neutralized, and
    everything it reads is a real object rather than a Mock whose iteration
    raises.
    """
    from academic_hunter.core.infra.state import SearchState

    hunter = MagicMock()
    hunter.connectors = connectors
    hunter.state = SearchState()
    hunter.blocked_sources = set()
    hunter.settings = settings if settings is not None else {"ablation": {"mode": "keyword"}}
    hunter.anchors = {"Topic": ["cbdc"]}
    hunter.tech_strings = {"Topic": ["cbdc"]}
    hunter.consolidated_results = {}
    hunter.semantic_screener = None
    for suffix in ("needs_credential", "keyless"):
        getattr(hunter, f"fetch_{suffix}").return_value = []
    return hunter


def _run_to_completion(hunter, limit_per_source=1):
    from academic_hunter.core.pipeline.manager import SearchPipeline

    pipeline = SearchPipeline(hunter)
    with patch.object(pipeline, "_recompute_ranks"), \
         patch.object(pipeline, "_index_results"), \
         patch.object(pipeline, "_ingest_full_text"), \
         patch.object(pipeline, "_auto_export_to_obsidian"), \
         patch("academic_hunter.core.pipeline.manager.run_dir_for"):
        return pipeline.run(limit_per_source=limit_per_source)


class _NeedsACredential:
    fetch_suffix = "needs_credential"
    domain = "api.needs.example.org"
    REASON = "no API key. Set NEEDS_KEY in the environment."

    @classmethod
    def unavailable_reason(cls, settings):
        return "" if settings.get("needs_key") else cls.REASON


class _KeylessIsFine:
    fetch_suffix = "keyless"
    domain = "api.keyless.example.org"

    @classmethod
    def unavailable_reason(cls, settings):
        return ""


def test_a_source_that_cannot_run_never_gets_a_thread():
    """The gate that keeps a failing source from reporting a zero as a finding.

    Measured: Semantic Scholar without a key took three 429s, was blocked
    mid-run, and the reply still said `Semantic Scholar: 0` -- which reads
    exactly like a source that was asked and found nothing. Not calling it is
    the fix; the reason is what makes the absence legible.
    """
    hunter = _hunter_for_a_full_run(
        {"Needs Credential": _NeedsACredential(), "Keyless": _KeylessIsFine()}
    )

    _run_to_completion(hunter)

    hunter.fetch_needs_credential.assert_not_called()
    hunter.fetch_keyless.assert_called_once()
    assert hunter.state.stats["unavailable_sources"] == {
        "Needs Credential": _NeedsACredential.REASON
    }


def test_the_gate_is_re_answered_by_every_run():
    """A key configured between two runs has to be honoured by the second one.

    Answered once at construction it would be frozen for the life of the
    server, and `update_config` writing a credential would change nothing until
    a restart -- which is the shape of defect this whole change is about.
    """
    hunter = _hunter_for_a_full_run(
        {"Needs Credential": _NeedsACredential()},
        settings={"ablation": {"mode": "keyword"}, "needs_key": True},
    )

    _run_to_completion(hunter)

    hunter.fetch_needs_credential.assert_called_once()
    assert hunter.state.stats["unavailable_sources"] == {}


def test_a_run_writes_the_prisma_flow_once():
    """The same flow was written twice, with the same timestamp.

    The first call ran before the eligibility filter, so the file it produced
    was named for the run and showed the identification counters as if the
    screening had not happened; the second overwrote it. A reader who opened the
    file between the two calls got the wrong one.
    """
    from academic_hunter.core.pipeline.manager import SearchPipeline

    hunter = _make_hunter_with_results({"a": {"Relevance_Score": 9.0}})
    hunter.connectors = {}
    hunter.settings = {}

    SearchPipeline(hunter).run()

    assert hunter.export_results.call_count == 1, "the run did not reach its exports"
    assert hunter.generate_prisma_report.call_count == 1, (
        "the run wrote the PRISMA flow more than once"
    )
