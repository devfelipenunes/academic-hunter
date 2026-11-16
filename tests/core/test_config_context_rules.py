"""`context_rules` belongs under `settings`, and it has to actually be read.

Both shipped templates carry the rules inside ``settings``, while ``load`` read
them from the top level and ``save`` wrote them back there. A nested block was
therefore dead: an operator editing the rules where the templates put them
changed nothing, and a stale top-level key silently decided which rules applied.
"""

import json
import logging

import pytest

from academic_hunter.core.infra.config import HunterConfig

RULES = {"drex": ["cbdc", "payment"]}
STALE = {"delegation": ["authority"]}


def _write(path, payload):
    path.write_text(json.dumps(payload))
    return path


@pytest.fixture
def nested(tmp_path):
    return _write(tmp_path / "nested.json", {
        "settings": {"context_rules": dict(RULES)},
        "anchors": {"cat": ["ledger"]},
        "technical_strings": {}, "technical_weights": {},
    })


def test_the_nested_block_is_read(nested):
    assert HunterConfig(config_path=str(nested)).context_rules == RULES


def test_the_top_level_key_is_still_read(tmp_path):
    """A file that predates the move keeps working."""
    path = _write(tmp_path / "old.json", {
        "settings": {}, "anchors": {}, "technical_strings": {},
        "technical_weights": {}, "context_rules": dict(STALE),
    })

    assert HunterConfig(config_path=str(path)).context_rules == STALE


def test_a_nested_block_wins_over_a_stale_top_level_one(tmp_path):
    """The file carried both; the one where the templates put it is the one meant."""
    path = _write(tmp_path / "both.json", {
        "settings": {"context_rules": dict(RULES)},
        "anchors": {}, "technical_strings": {}, "technical_weights": {},
        "context_rules": dict(STALE),
    })

    assert HunterConfig(config_path=str(path)).context_rules == RULES


def test_two_different_blocks_are_reported_at_load(tmp_path, caplog):
    """Which rules apply changed, and nothing said so.

    Measured on this repo's own `config.json`: the blockchain rules sat at the
    top level, written there by the published wheel, and the old DLT rules
    (delegation, mandate, drex) sat nested. Preferring the nested copy is right,
    but it means switching builds -- clone instead of wheel -- silently swaps
    the rules in effect. Silently is the part being fixed.
    """
    path = _write(tmp_path / "both.json", {
        "settings": {"context_rules": dict(RULES)},
        "anchors": {}, "technical_strings": {}, "technical_weights": {},
        "context_rules": dict(STALE),
    })

    with caplog.at_level(logging.WARNING):
        HunterConfig(config_path=str(path))

    assert "two different `context_rules`" in caplog.text
    assert "1 rule(s) under `settings`, 1 at the top level" in caplog.text


def test_one_block_alone_is_not_reported(tmp_path, caplog):
    """The warning has to mean something, so it cannot fire on a clean file."""
    path = _write(tmp_path / "clean.json", {
        "settings": {"context_rules": dict(RULES)},
        "anchors": {}, "technical_strings": {}, "technical_weights": {},
    })

    with caplog.at_level(logging.WARNING):
        HunterConfig(config_path=str(path))

    assert "context_rules" not in caplog.text


def test_two_identical_blocks_are_not_reported(tmp_path, caplog):
    """Same rules in both places is untidy, not ambiguous -- nothing changes."""
    path = _write(tmp_path / "same.json", {
        "settings": {"context_rules": dict(RULES)},
        "anchors": {}, "technical_strings": {}, "technical_weights": {},
        "context_rules": dict(RULES),
    })

    with caplog.at_level(logging.WARNING):
        made = HunterConfig(config_path=str(path))

    assert made.context_rules == RULES
    assert "context_rules" not in caplog.text


def test_the_two_spellings_are_one_dict(nested):
    """Otherwise an edit through `settings` would not reach the scorer."""
    made = HunterConfig(config_path=str(nested))

    assert made.settings["context_rules"] is made.context_rules


def test_saving_writes_the_rules_nested(nested):
    made = HunterConfig(config_path=str(nested))

    made.save()

    written = json.loads(nested.read_text())
    assert written["settings"]["context_rules"] == RULES
    assert "context_rules" not in written


def test_a_mixed_case_rule_key_still_fires(tmp_path):
    """A capitalised key was looked up verbatim and never found.

    The scorer lower-cases the matched term before ``context_rules.get(term)``,
    so a rule written ``Drex`` missed every time, ``if required_keywords`` was
    false, and the contextual check was skipped in silence — the term passed
    unchallenged, which is the failure the check exists to prevent.
    """
    from academic_hunter.core.nlp import AcademicScorer

    path = _write(tmp_path / "mixed.json", {
        "settings": {"context_rules": {"Drex": ["CBDC"]}},
        "anchors": {}, "technical_strings": {}, "technical_weights": {},
    })

    made = HunterConfig(config_path=str(path))
    scorer = AcademicScorer(
        made.anchors, made.tech_strings, made.tech_weights, made.context_rules, {}
    )

    assert scorer.validate_anchor_context("a cbdc payment system", "Drex") is True
    assert scorer.validate_anchor_context("unrelated prose", "Drex") is False


def test_a_capitalised_keyword_still_counts_as_context(tmp_path):
    """The other direction: the keywords were compared without folding either."""
    from academic_hunter.core.nlp import AcademicScorer

    path = _write(tmp_path / "loud.json", {
        "settings": {"context_rules": {"drex": ["CBDC"]}},
        "anchors": {}, "technical_strings": {}, "technical_weights": {},
    })

    made = HunterConfig(config_path=str(path))
    scorer = AcademicScorer(
        made.anchors, made.tech_strings, made.tech_weights, made.context_rules, {}
    )

    assert scorer.validate_anchor_context("a cbdc payment system", "drex") is True


def test_the_rules_are_folded_when_written_straight_to_the_attribute(nested):
    """``update_config`` and the restore assign the attribute, not the file."""
    made = HunterConfig(config_path=str(nested))

    made.context_rules = {"Drex": ["CBDC"]}

    assert made.context_rules == {"drex": ["cbdc"]}
    assert made.settings["context_rules"] is made.context_rules


def test_a_saved_rule_reaches_the_scorer(nested):
    """The end of the chain: the rule decides whether a match counts."""
    from academic_hunter.core.nlp import AcademicScorer

    made = HunterConfig(config_path=str(nested))
    scorer = AcademicScorer(
        made.anchors, made.tech_strings, made.tech_weights, made.context_rules, {}
    )

    assert scorer.validate_anchor_context("a cbdc payment system", "drex") is True
    assert scorer.validate_anchor_context("unrelated prose", "drex") is False


def test_context_can_be_required_in_the_title(tmp_path):
    """A narrow topic can reject papers whose only scope match is incidental in the abstract."""
    from academic_hunter.core.nlp import AcademicScorer
    from academic_hunter.core.screening.validators import PaperValidator

    path = _write(tmp_path / "title-context.json", {
        "settings": {
            "context_rules": {"microplastic": ["freshwater", "river", "lake"]},
            "context_rules_title_only": True,
            "context_exclude_title_terms": ["marine", "coastal", "estuary"],
        },
        "anchors": {"Pollutant": ["microplastic"]},
        "technical_strings": {},
        "technical_weights": {"microplastic": 5},
    })
    config = HunterConfig(config_path=str(path))
    scorer = AcademicScorer(
        config.anchors, config.tech_strings, config.tech_weights, config.context_rules, config.settings
    )
    validator = PaperValidator(config, scorer)

    paper = {
        "Title": "Microplastic particles in coastal sediments",
        "Abstract": "We compare marine samples with freshwater river samples.",
    }
    assert validator.match_anchor(paper) == ("", "")

    paper["Title"] = "Microplastic particles in a freshwater river"
    assert validator.match_anchor(paper) == ("Pollutant", "microplastic")

    paper["Title"] = "Microplastic particles in a freshwater river estuary"
    assert validator.match_anchor(paper) == ("", "")


def test_abstract_context_remains_the_default(tmp_path):
    """Existing configs keep their established title plus abstract behavior."""
    from academic_hunter.core.nlp import AcademicScorer
    from academic_hunter.core.screening.validators import PaperValidator

    path = _write(tmp_path / "default-context.json", {
        "settings": {"context_rules": {"microplastic": ["freshwater", "river"]}},
        "anchors": {"Pollutant": ["microplastic"]},
        "technical_strings": {},
        "technical_weights": {"microplastic": 5},
    })
    config = HunterConfig(config_path=str(path))
    scorer = AcademicScorer(
        config.anchors, config.tech_strings, config.tech_weights, config.context_rules, config.settings
    )
    validator = PaperValidator(config, scorer)

    paper = {
        "Title": "Microplastic particles in coastal sediments",
        "Abstract": "We compare marine samples with freshwater river samples.",
    }
    assert validator.match_anchor(paper) == ("Pollutant", "microplastic")


def test_context_keywords_do_not_match_inside_other_words():
    from academic_hunter.core.nlp import AcademicScorer

    scorer = AcademicScorer({}, {}, {}, {"plastic debris": ["river", "rivers"]}, {})

    assert scorer.validate_anchor_context("drivers of plastic debris on beaches", "plastic debris") is False
    assert scorer.validate_anchor_context("plastic debris in rivers", "plastic debris") is True


def test_title_exclusions_match_whole_terms_and_plural_variants(tmp_path):
    from academic_hunter.core.nlp import AcademicScorer
    from academic_hunter.core.screening.validators import PaperValidator

    path = _write(tmp_path / "title-exclusions.json", {
        "settings": {
            "context_rules": {"microplastic": ["freshwater", "river"]},
            "context_rules_title_only": True,
            "context_exclude_title_terms": ["marine", "estuary", "estuaries"],
        },
        "anchors": {"Pollutant": ["microplastic"]},
        "technical_strings": {},
        "technical_weights": {"microplastic": 5},
    })
    config = HunterConfig(config_path=str(path))
    scorer = AcademicScorer(
        config.anchors, config.tech_strings, config.tech_weights, config.context_rules, config.settings
    )
    validator = PaperValidator(config, scorer)

    paper = {"Title": "Microplastic debris in a submarine freshwater river", "Abstract": ""}
    assert validator.match_anchor(paper) == ("Pollutant", "microplastic")

    paper["Title"] = "Microplastic debris in freshwater river estuaries"
    assert validator.match_anchor(paper) == ("", "")


def test_anchor_rejection_reports_auditable_reason(tmp_path):
    from academic_hunter.core.nlp import AcademicScorer
    from academic_hunter.core.screening.validators import PaperValidator

    path = _write(tmp_path / "rejection-reasons.json", {
        "settings": {
            "context_rules": {"microplastic": ["freshwater", "river"]},
            "context_rules_title_only": True,
            "context_exclude_title_terms": ["marine"],
        },
        "anchors": {"Pollutant": ["microplastic"]},
        "technical_strings": {},
        "technical_weights": {"microplastic": 5},
    })
    config = HunterConfig(config_path=str(path))
    scorer = AcademicScorer(
        config.anchors, config.tech_strings, config.tech_weights, config.context_rules, config.settings
    )
    validator = PaperValidator(config, scorer)

    assert validator.anchor_rejection_detail({"Title": "Drivers of plastic debris"}) == "anchor_missing"
    assert validator.anchor_rejection_detail({"Title": "Microplastic in an aquatic system"}) == "context_missing"
    assert validator.anchor_rejection_detail({"Title": "Microplastic in a marine river"}) == "title_exclusion"
