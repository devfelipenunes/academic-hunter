"""Um título quebrado em duas linhas vale o mesmo que o mesmo título numa linha.

Os conectores entregam texto como ele veio da API, e o arXiv — como quase todo
Atom — quebra títulos e abstracts com indentação. A normalização trocava `\\n`
por um espaço, o que deixa a **indentação da linha seguinte** no meio do texto.
"""

import pytest

from academic_hunter.core.models import Paper
from academic_hunter.core.models.utils import normalize_doi
from academic_hunter.core.nlp import AcademicScorer

WRAPPED = {
    "Title": "A study of blockchain\n      interoperability",
    "Abstract": "We measure throughput\n        across ledgers.",
}
FLAT = {
    "Title": "A study of blockchain interoperability",
    "Abstract": "We measure throughput across ledgers.",
}


def test_a_title_wrapped_across_lines_has_single_spaces():
    assert Paper(dict(WRAPPED))["Title"] == FLAT["Title"]


def test_an_abstract_wrapped_across_lines_has_single_spaces():
    assert Paper(dict(WRAPPED))["Abstract"] == FLAT["Abstract"]


def test_the_wrap_is_not_carried_into_the_displayed_text():
    """Runs of spaces survive into the CSV, the .bib and the agent's context."""
    title = Paper(dict(WRAPPED))["Title"]

    assert "  " not in title
    assert "\n" not in title


@pytest.mark.parametrize(
    "raw",
    [
        "https://dx.doi.org/10.1234/ABC",
        "http://dx.doi.org/10.1234/ABC",
        "https://doi.org/10.1234/ABC",
        "http://doi.org/10.1234/ABC",
        "doi:10.1234/ABC",
        "  10.1234/ABC  ",
    ],
)
def test_every_spelling_of_a_doi_normalises_to_one_identifier(raw):
    """Two spellings of one DOI must not become two papers.

    The known defect: `dx.doi.org/` was stripped *after* the scheme, so
    `https://dx.doi.org/10.1234/ABC` became `https://10.1234/abc`. This string is
    what the identity index, the deduplication and the exported `.bib` all key
    on, so the corruption produced a second paper for the same work.
    """
    assert normalize_doi(raw) == "10.1234/abc"


def test_a_missing_doi_stays_empty():
    assert normalize_doi("") == ""
    assert normalize_doi(None) == ""


def _processor():
    import json
    import tempfile
    import threading
    from pathlib import Path

    from academic_hunter.core.infra import HunterConfig, SearchState
    from academic_hunter.core.screening.processor import PaperProcessor

    settings = {
        "settings": {"min_relevance_score": 0.0, "start_year": 2024},
        "anchors": {"cat": ["blockchain interoperability"]},
        "technical_strings": {},
        "technical_weights": {},
    }
    path = Path(tempfile.mkdtemp()) / "config.json"
    path.write_text(json.dumps(settings))
    config = HunterConfig(config_path=str(path))
    scorer = AcademicScorer(
        config.anchors, config.tech_strings, config.tech_weights,
        config.context_rules, config.settings,
    )
    return PaperProcessor(
        state=SearchState(), scorer=scorer, config=config,
        connectors={}, lock=threading.RLock(),
    )


def test_the_pipeline_normalises_what_a_connector_hands_it():
    """The scorer reads the raw paper dict, not the stored `Paper`.

    So normalising in the model is not enough: whatever a connector returns has
    to be clean *before* it reaches scoring, or the next connector repeats the
    arXiv defect and nothing catches it.
    """
    processor = _processor()

    processor.process(
        paper={
            "Title": "A study of blockchain\n      interoperability",
            "Abstract": "Throughput\n        across ledgers.",
            "Year": "2024", "Source": "Mock", "Citations": 0,
            "Type": "article", "Venue": "V", "URL": "u",
        },
        anchor_cat="cat", tech_cat="cat",
        anchor_list=["blockchain interoperability"], tech_list=[],
    )

    stored = next(iter(processor.state.consolidated_results.values()))
    assert stored["Title"] == "A study of blockchain interoperability"
    assert stored["Abstract"] == "Throughput across ledgers."


def test_a_two_word_term_split_by_the_wrap_still_matches():
    """The scorer matches terms with a literal space, so the wrap broke the match.

    An anchor or technical term of two words that straddled a line break scored
    zero — the paper dropped out of the anchor filter, or ranked below one that
    happened not to wrap.
    """
    scorer = AcademicScorer(
        anchors={},
        tech_strings={},
        tech_weights={"blockchain interoperability": 5.0},
        context_rules={},
        settings={"title_multiplier": 1.5},
    )

    wrapped = Paper(dict(WRAPPED))["Title"]
    flat = Paper(dict(FLAT))["Title"]

    assert scorer.calculate_score(wrapped, "", 0) == scorer.calculate_score(flat, "", 0)
    assert scorer.calculate_score(flat, "", 0) > 0, "the term matched nothing at all"
