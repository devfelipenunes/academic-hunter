"""One collection per review: the name has to be legal, stable and derivable.

A single shared ``papers`` collection held 1040 papers from two searches, so
clustering, trends and duplicate detection described both of them while reading
as statements about the current review. The fix is a collection per review, and
what makes it work is that the name is *derived once and stored* rather than
computed at each read -- a name that moved between runs would leave the corpus
where nothing looks for it.
"""

import json
import logging

import pytest

from academic_hunter.core.infra.config import HunterConfig
from academic_hunter.core.ports.vector_store import (
    LEGACY_COLLECTION,
    is_valid_collection_name,
    review_collection_name,
)


class TestChromaRules:
    """The constraints are ChromaDB's, and a name that breaks one is refused at
    the first write -- after the search has already been paid for."""

    @pytest.mark.parametrize("name", ["papers", "review_a1", "a.b-c_d", "abc"])
    def test_names_chromadb_accepts(self, name):
        assert is_valid_collection_name(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            "",
            "ab",
            "a" * 64,
            " review",
            "review ",
            "_review",
            "review_",
            ".review",
            "review.",
            "-review",
            "review-",
            "review..x",
            "review x",
            "review/x",
            "review:1",
            "reviewé",
        ],
    )
    def test_names_chromadb_rejects(self, name):
        assert is_valid_collection_name(name) is False

    def test_a_non_string_is_not_a_name(self):
        assert is_valid_collection_name(None) is False
        assert is_valid_collection_name(7) is False


class TestDerivation:
    def test_a_topic_becomes_a_readable_slug(self):
        assert review_collection_name("blockchain e IA") == "review_blockchain_e_ia"

    def test_accents_and_punctuation_collapse_rather_than_vanish(self):
        assert review_collection_name("Delegação de Autoridade (DLT)!") == (
            "review_delega_o_de_autoridade_dlt"
        )

    def test_anchors_are_the_fallback_source(self):
        assert review_collection_name("", {"A": ["cbdc"], "B": ["distributed ledger"]}) == (
            "review_cbdc_distributed_ledger"
        )

    def test_the_topic_wins_over_the_anchors(self):
        assert review_collection_name("Blockchain", {"A": ["cbdc"]}) == (
            "review_blockchain"
        )

    def test_nothing_derivable_returns_empty_rather_than_a_guess(self):
        """`""` lets the caller keep the name it has. A guess would move a corpus.

        The caller is `update_config`, which sees `""` and leaves an established
        review alone; inventing `review_untitled` there would point the next run
        at a new collection while the real one sat unread.
        """
        assert review_collection_name("") == ""
        assert review_collection_name("   ") == ""
        assert review_collection_name("???") == ""
        assert review_collection_name("", {}) == ""
        assert review_collection_name("", {"A": []}) == ""

    def test_a_long_topic_still_lands_inside_the_limit(self):
        name = review_collection_name(" ".join(["distributed", "ledger", "consensus"] * 8))

        assert is_valid_collection_name(name), name
        assert len(name) <= 63
        assert name.startswith("review_")

    def test_the_truncation_never_leaves_a_separator_at_an_end(self):
        """A 63-character cut can land on the underscore that follows a word."""
        for repeat in range(1, 40):
            name = review_collection_name("_".join(["ab"] * repeat))
            if name:
                assert is_valid_collection_name(name), (repeat, name)

    def test_every_derived_name_is_one_chromadb_accepts(self):
        for topic in (
            "AI", "a", "ab", "x" * 200, "CBDC & stablecoins",
            "  leading and trailing  ", "São Paulo", "2024 review",
        ):
            name = review_collection_name(topic)
            if name:
                assert is_valid_collection_name(name), (topic, name)


class TestConfigHoldsIt:
    def _config(self, tmp_path, settings):
        path = tmp_path / "config.json"
        path.write_text(json.dumps({
            "settings": settings, "anchors": {}, "technical_strings": {},
            "technical_weights": {},
        }), encoding="utf-8")
        return HunterConfig(config_path=str(path))

    def test_a_configured_name_is_used(self, tmp_path):
        made = self._config(tmp_path, {"collection_name": "review_blockchain_e_ia"})

        assert made.collection_name() == "review_blockchain_e_ia"

    def test_a_config_without_one_still_reads_where_its_papers_are(self, tmp_path):
        """Everything indexed before this existed is in `papers`, and reading
        anywhere else would report the review as empty."""
        made = self._config(tmp_path, {})

        assert made.collection_name() == LEGACY_COLLECTION

    def test_an_unusable_name_is_reported_and_the_readable_one_used(
        self, tmp_path, caplog
    ):
        """Falling back in silence is how "0 papers" becomes unexplainable."""
        made = self._config(tmp_path, {"collection_name": "not a legal name!"})

        with caplog.at_level(logging.WARNING):
            assert made.collection_name() == LEGACY_COLLECTION

        assert "not a legal name!" in caplog.text
        assert "will not accept" in caplog.text

    def test_a_valid_name_is_not_reported(self, tmp_path, caplog):
        made = self._config(tmp_path, {"collection_name": "review_x"})

        with caplog.at_level(logging.WARNING):
            made.collection_name()

        assert "collection_name" not in caplog.text

    def test_the_name_survives_a_save_and_reload(self, tmp_path):
        made = self._config(tmp_path, {})
        made.settings["collection_name"] = "review_blockchain_e_ia"
        made.save()

        reloaded = HunterConfig(config_path=str(made.config_path))

        assert reloaded.collection_name() == "review_blockchain_e_ia"
