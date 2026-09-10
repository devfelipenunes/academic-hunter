"""``SearchState.reset`` must clear the objects the connectors already hold."""

from academic_hunter.core.infra import SearchState


def test_reset_keeps_the_objects_the_connectors_hold():
    """The connectors are built once, with these very objects as arguments.

    Rebinding the attribute instead of clearing it leaves them appending to the
    old list — which silently emptied the PRISMA "Search Queries History"
    section of every run, and never reset the per-domain pacing.
    """
    state = SearchState()
    history = state.query_history  # what a connector was handed at construction
    pacing = state.last_request_by_domain

    history.append({"Source": "arXiv", "Query": "ledgers"})
    pacing["export.arxiv.org"] = 1234.5

    state.reset(["arXiv"])

    assert history == [], "the connector's query history was not cleared"
    assert pacing == {}, "the connector's pacing map was not cleared"
    assert state.query_history is history
    assert state.last_request_by_domain is pacing


def test_reset_clears_the_previous_run():
    state = SearchState()
    state.consolidated_results["slug"] = {"Title": "X"}
    state.seen_ids.add("slug")
    state.stats["identified"]["arXiv"] = 7

    state.reset(["arXiv"])

    assert state.consolidated_results == {}
    assert state.seen_ids == set()
    assert state.stats["identified"] == {"arXiv": 0}
