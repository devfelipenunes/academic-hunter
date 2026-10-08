"""Two records of one study must leave one paper holding the better abstract.

The abstract is not decoration here. Its weighted tally of domain terms is
``_kw_score``, which decides whether the paper is in the review at all -- so a
merge that keeps the longer text instead of the better one can drop the paper.
Both defects below were measured on two databases returning one study between
them: the paper kept the abstract that matched fewer terms, and half the runs
lost it entirely to a race between the two copies.
"""

import json
import threading
import time

import pytest

from academic_hunter.core.infra import HunterConfig, SearchState
from academic_hunter.core.models import Paper
from academic_hunter.core.models.strategies import strategy_url
from academic_hunter.core.nlp import AcademicScorer
from academic_hunter.core.screening.processor import PaperProcessor
from academic_hunter.core.screening.resolvers import PaperResolver

CONFIG = {
    "settings": {
        "title_multiplier": 1.5,
        "score_precision": 1,
        "min_relevance_score": 5.0,
    },
    "anchors": {"cat": ["anchor"]},
    "technical_strings": {"cat": ["tech"]},
    "technical_weights": {"anchor": 1.0, "tech": 10.0},
}

POOR = {
    "Title": "Research",
    "Abstract": "Nothing interesting here, just an anchor.",
    "Year": "2024",
    "Source": "Source1",
    "Citations": 0,
    "Type": "article",
    "Venue": "Venue1",
    "URL": "url1",
}

RICH = {
    "Title": "Research",
    "Abstract": "This is about tech and anchor.",
    "Year": "2024",
    "Source": "Source2",
    "Citations": 5,
    "Type": "article",
    "Venue": "Venue2",
    "URL": "url2",
}


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(CONFIG))
    return HunterConfig(config_path=str(path))


def make_scorer(config):
    return AcademicScorer(
        anchors=config.anchors,
        tech_strings=config.tech_strings,
        tech_weights=config.tech_weights,
        context_rules=config.context_rules,
        settings=config.settings,
    )


def make_processor(config):
    lock = threading.RLock()
    scorer = make_scorer(config)
    state = SearchState()
    state.reset([])
    return PaperProcessor(state, scorer, config, {}, lock), scorer, state


def make_resolver(config):
    lock = threading.RLock()
    scorer = make_scorer(config)
    return PaperResolver(
        state=SearchState(),
        scorer=scorer,
        config=config,
        connectors={},
        lock=lock,
    ), scorer


def test_the_shorter_abstract_wins_when_it_matches_more_terms(config):
    """Length is a tie-break, not an override.

    The incoming abstract is nine characters shorter and worth eleven times the
    term weight. Length alone used to take it, and the paper then carried the
    abstract that matches one configured term out of two.
    """
    resolver, scorer = make_resolver(config)
    existing = dict(POOR)

    resolver.resolve_existing_duplicate(existing, dict(RICH), "cat", "cat", "Source2")

    assert existing["Abstract"] == RICH["Abstract"], (
        "the merge kept the longer abstract over the one that scores higher"
    )
    assert existing["_kw_score"] >= 5.0


def test_the_better_abstract_survives_the_merge_in_both_arrival_orders(config):
    """Whichever copy arrives first, the pair converges on the same paper."""
    resolver, scorer = make_resolver(config)
    existing = dict(RICH)

    resolver.resolve_existing_duplicate(existing, dict(POOR), "cat", "cat", "Source1")

    assert existing["Abstract"] == RICH["Abstract"], (
        "the longer abstract overwrote the one that scores higher"
    )
    assert existing["_kw_score"] >= 5.0


@pytest.mark.parametrize("first,second", [(POOR, RICH), (RICH, POOR)])
def test_the_stored_score_is_the_score_of_the_stored_abstract(config, first, second):
    """The invariant the old merge broke: one number, one text.

    ``_kw_score`` was carried over from the first copy while the abstract came
    from the second, so the paper was judged on a tally of words it does not
    hold -- and the embedding was probed on a third text again.
    """
    resolver, scorer = make_resolver(config)
    existing = dict(first)

    resolver.resolve_existing_duplicate(existing, dict(second), "cat", "cat", "Other")

    recomputed = scorer.calculate_score(
        existing["Title"], existing["Abstract"], existing["Citations"]
    )
    assert existing["_kw_score"] == recomputed


def test_a_copy_arriving_mid_registration_is_merged_and_not_dropped(config):
    """The window between claiming a study and registering it is not a no-man's-land.

    The claimant holds the id while it is still scoring itself -- the embedding
    runs outside the lock on purpose -- so a second copy can find the id taken,
    nothing under it, and no exclusion recorded. It used to be discarded there,
    on a ``debug`` line, as if it were a third copy of a promotion somebody else
    was handling: not a duplicate dropped, a paper dropped.

    The first copy is held inside ``register_new_paper`` to open that window
    deliberately instead of hoping for it.
    """
    processor, scorer, state = make_processor(config)
    real_register = processor.resolver.register_new_paper
    claimed = threading.Event()
    release = threading.Event()

    def hold(*args, **kwargs):
        claimed.set()
        release.wait(10)
        return real_register(*args, **kwargs)

    processor.resolver.register_new_paper = hold

    first = threading.Thread(
        target=lambda: processor.process(dict(POOR), "cat", "cat", ["anchor"], ["tech"])
    )
    first.start()
    assert claimed.wait(10), "the first copy never reached registration"

    second = threading.Thread(
        target=lambda: processor.process(dict(RICH), "cat", "cat", ["anchor"], ["tech"])
    )
    second.start()
    time.sleep(0.2)
    release.set()
    first.join(15)
    second.join(15)

    assert not first.is_alive() and not second.is_alive(), (
        "a worker thread never came back from the merge"
    )

    merged = list(state.consolidated_results.values())
    assert len(merged) == 1, "the two copies left something other than one paper"
    assert merged[0]["Abstract"] == RICH["Abstract"], (
        "the copy that arrived while the first was being registered was discarded"
    )
    assert not state.pending_registrations, (
        "the claim outlived the registration that was supposed to settle it"
    )


ARXIV_COPY = {
    "Title": "Large Language Model-Powered Smart Contract Vulnerability Detection",
    "Abstract": "We detect smart contract vulnerabilities with a language model.",
    "Year": "2023",
    "Source": "ArXiv",
    "Citations": 0,
    "Type": "article",
    "Venue": "ArXiv",
    "URL": "http://arxiv.org/abs/2310.01152v2",
}
CORE_COPY = {
    **ARXIV_COPY,
    "Source": "CORE",
    "Venue": "Unknown Venue",
    "URL": "https://core.ac.uk/works/391546543",
}


@pytest.mark.parametrize(
    "first,second",
    [(ARXIV_COPY, CORE_COPY), (CORE_COPY, ARXIV_COPY)],
    ids=["arxiv-first", "core-first"],
)
def test_the_arxiv_url_survives_the_merge_whichever_copy_arrives_first(config, first, second):
    """The citation backfill reads this URL to decide what to ask a source about.

    One preprint's two copies do not carry equivalent URLs: the arXiv copy
    addresses the work, the CORE copy is a landing page that yields no identifier
    at all. Keeping whichever arrived first made the identifier -- and so the
    citation count -- a coin flip between two mining threads. Measured over seven
    runs of one corpus: the same paper reported 9 citations or 0, and the
    provenance counters moved with it.
    """
    resolver, _ = make_resolver(config)
    existing = dict(first)

    resolver.resolve_existing_duplicate(existing, dict(second), "cat", "cat", second["Source"])

    assert existing["URL"] == ARXIV_COPY["URL"], (
        "the merge kept the URL that resolves to nothing"
    )


def test_two_landing_pages_converge_on_one_url_in_either_order(config):
    """Neither addresses the work, so the rule only has to pick the same one twice."""
    resolver, _ = make_resolver(config)

    forward = dict(POOR)
    resolver.resolve_existing_duplicate(forward, dict(RICH), "cat", "cat", "Source2")

    backward = dict(RICH)
    resolver.resolve_existing_duplicate(backward, dict(POOR), "cat", "cat", "Source1")

    assert forward["URL"] == backward["URL"], (
        "the stored url still depends on which copy arrived first"
    )


def test_a_url_that_addresses_the_work_beats_a_landing_page():
    """An address beats a landing page, in either argument order."""
    assert strategy_url(CORE_COPY["URL"], ARXIV_COPY["URL"]) == ARXIV_COPY["URL"]
    assert strategy_url(ARXIV_COPY["URL"], CORE_COPY["URL"]) == ARXIV_COPY["URL"]


def test_two_urls_that_address_nothing_settle_the_same_way_round():
    """Arbitrary, but the same side every run -- what makes two runs comparable."""
    assert strategy_url("https://b.example/2", "https://a.example/1") == "https://a.example/1"
    assert strategy_url("https://a.example/1", "https://b.example/2") == "https://a.example/1"


def test_an_empty_url_never_wins_over_a_present_one():
    assert strategy_url("", ARXIV_COPY["URL"]) == ARXIV_COPY["URL"]
    assert strategy_url(CORE_COPY["URL"], "") == CORE_COPY["URL"]
    assert strategy_url("", "") == ""


PREPRINT_COPY = {
    "Title": "A study",
    "Peer_Reviewed": "No (Preprint)",
    "Year": "2021",
    "Source": "ArXiv",
}
PUBLISHED_COPY = {
    "Title": "A study",
    "Peer_Reviewed": "Yes",
    "Year": "2023",
    "Source": "Crossref",
}


def _merged(first, second):
    paper = Paper(dict(first))
    paper.merge(dict(second), "cat", "cat")
    return paper["Year"]


@pytest.mark.parametrize("first,second", [(PREPRINT_COPY, PUBLISHED_COPY), (PUBLISHED_COPY, PREPRINT_COPY)])
def test_the_year_of_the_published_version_is_the_one_that_survives(first, second):
    """``Year`` had no merge strategy, so the first copy registered won it.

    The two copies do not disagree about the year of the work so much as
    describe two versions of it: the arXiv posting is earlier than the paper it
    became, and the year a review cites is the year of the published version.
    """
    assert _merged(first, second) == "2023"


def test_an_unstated_year_never_wins_over_a_stated_one():
    """A copy that carries no year is not claiming the work has none."""
    assert _merged({"Year": None, "Peer_Reviewed": "No (Preprint)"}, {"Year": "2023", "Peer_Reviewed": "No (Preprint)"}) == "2023"
    assert _merged({"Year": "2023", "Peer_Reviewed": "No (Preprint)"}, {"Year": None, "Peer_Reviewed": "No (Preprint)"}) == "2023"


def test_two_copies_of_one_status_settle_on_one_year_in_either_order():
    """Arbitrary, but the same side twice -- what makes two runs comparable."""
    forward = _merged(PREPRINT_COPY, {**PREPRINT_COPY, "Year": "2022"})
    backward = _merged({**PREPRINT_COPY, "Year": "2022"}, PREPRINT_COPY)

    assert forward == backward == "2021"


TWO_GROUPS = {
    "settings": {
        "title_multiplier": 1.5,
        "score_precision": 1,
        "min_relevance_score": 5.0,
    },
    "anchors": {"cat": ["anchor"], "other": ["ledger"]},
    "technical_strings": {"tech": ["tech"], "other_tech": ["watchtower"]},
    "technical_weights": {"anchor": 1.0, "ledger": 1.0, "tech": 10.0, "watchtower": 10.0},
}


def two_group_resolver(tmp_path):
    path = tmp_path / "two.json"
    path.write_text(json.dumps(TWO_GROUPS))
    return make_resolver(HunterConfig(config_path=str(path)))


def test_the_anchor_terms_of_both_copies_survive_the_merge(tmp_path):
    """Measured on the delivered run: 57 of 310 rows list two anchor categories
    and the terms of only one of them.

    ``Anchor_Category`` accumulated every group the work was found under while
    ``Anchor_Terms`` kept the first copy's and nothing else, because the
    duplicate path never ran the validator and so never computed the incoming
    copy's match. Two groups on a row is a claim about why the paper is in the
    review; listing one group's terms under it is half the evidence.
    """
    resolver, _ = two_group_resolver(tmp_path)
    existing = Paper({**POOR, "Anchor_Category": "cat", "Anchor_Terms": "anchor"})
    incoming = {"Title": "Research", "Abstract": "This one is about ledger.", "Source": "Source2"}

    resolver.resolve_existing_duplicate(existing, incoming, "other", "tech", "Source2")

    assert existing["Anchor_Category"] == "cat, other"
    assert existing["Anchor_Terms"] == "anchor, ledger"


def test_the_tech_terms_of_both_copies_survive_the_merge(tmp_path):
    resolver, _ = two_group_resolver(tmp_path)
    existing = Paper({**POOR, "Tech_Category": "tech", "Tech_Terms": "tech"})
    incoming = {
        "Title": "Research",
        "Abstract": "This one is about a watchtower.",
        "Source": "Source2",
    }

    resolver.resolve_existing_duplicate(
        existing, incoming, "cat", "other_tech", "Source2", ["watchtower"]
    )

    assert existing["Tech_Category"] == "other_tech, tech"
    assert existing["Tech_Terms"] == "tech, watchtower"


def test_terms_accumulate_the_same_way_whichever_copy_arrives_first(tmp_path):
    """The union, not the first value: two runs of one corpus have to agree."""
    forward = Paper({"Title": "T", "Anchor_Terms": "anchor"})
    forward.merge({"Anchor_Terms": "ledger"}, "cat", "cat")

    backward = Paper({"Title": "T", "Anchor_Terms": "ledger"})
    backward.merge({"Anchor_Terms": "anchor"}, "cat", "cat")

    assert forward["Anchor_Terms"] == backward["Anchor_Terms"] == "anchor, ledger"


def test_a_copy_that_matches_nothing_adds_no_terms(tmp_path):
    """An incoming copy whose text matches no anchor group contributes nothing,
    and must not blank out what the stored copy had."""
    resolver, _ = two_group_resolver(tmp_path)
    existing = Paper({**POOR, "Anchor_Terms": "anchor"})
    incoming = {"Title": "Research", "Abstract": "Nothing of the kind here.", "Source": "Source2"}

    resolver.resolve_existing_duplicate(existing, incoming, "cat", "tech", "Source2")

    assert existing["Anchor_Terms"] == "anchor"


def test_a_copy_with_no_state_of_peer_review_cannot_move_the_year():
    """The limit of the rule, pinned: what no source claims cannot be preferred.

    ``strategy_peer_reviewed`` reads an unknown status as the weakest claim, and
    this reads it the same way rather than inventing a second ordering for the
    same field.
    """
    assert _merged({"Year": "2021", "Peer_Reviewed": "No (Preprint)"}, {"Year": "2023"}) == "2021"
    assert _merged({"Year": "2021"}, {"Year": "2023", "Peer_Reviewed": "Yes"}) == "2023"
