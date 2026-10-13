"""Tests for configuration MCP tools (read_config, update_config, list_config_history, restore_config_by_id).

Uses mock_ctx from conftest and patches HunterConfig and MCPDatabaseManager.
"""

import json
from unittest.mock import patch

import pytest

from academic_hunter.interfaces.mcp.exceptions import MCPToolError
from academic_hunter.interfaces.mcp.schemas.config_schema import SearchConfigUpdate
from academic_hunter.interfaces.mcp.tools.configuration import (
    list_config_history,
    read_config,
    restore_config_by_id,
    update_config,
)


async def test_read_config(mock_hunter_config, mock_ctx):
    result = await read_config(mock_ctx)
    data = json.loads(result)
    assert "settings" in data
    assert data["settings"]["start_year"] == 2020
    mock_ctx.info.assert_called()


async def test_read_config_never_returns_api_keys(mock_ctx, tmp_path):
    """The config goes to the MCP client, so a credential in it would have leaked.

    Uses a real ``HunterConfig`` rather than the mock: the property only means
    something if the redaction actually runs.
    """
    from academic_hunter.core.infra.config import REDACTED, HunterConfig

    secret = "s2k-do-not-leak-this"
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "settings": {
                    "start_year": 2021,
                    "semantic_scholar_api_key": secret,
                    "api_keys": {"semantic_scholar": secret},
                },
                "anchors": {},
                "technical_strings": {},
                "technical_weights": {},
            }
        )
    )

    with patch(
        "academic_hunter.interfaces.mcp.tools.configuration.get_config",
        return_value=HunterConfig(config_path=str(path)),
    ):
        result = await read_config(mock_ctx)

    assert secret not in result, "the API key reached the MCP client"
    assert REDACTED in result, "the caller can still see that a key is configured"


async def test_read_config_failure(mock_ctx):
    with patch(
        "academic_hunter.core.infra.config.HunterConfig"
    ) as m:
        m.side_effect = RuntimeError("config.json missing")
        with pytest.raises(MCPToolError, match="config.json missing"):
            await read_config(mock_ctx)
    mock_ctx.error.assert_called()


async def test_update_config_and_history(mock_hunter_config, mock_mcp_db, mock_ctx):
    config_update = SearchConfigUpdate(
        topic="Test Topic",
        settings={"start_year": 2024},
        technical_weights={"new": 2.0},
    )
    result = await update_config(config_update, mock_ctx)
    assert "successfully" in result.lower()

    assert mock_hunter_config.settings["start_year"] == 2024
    assert mock_hunter_config.tech_weights["new"] == 2.0
    assert mock_mcp_db.save_config.call_count == 2
    mock_ctx.info.assert_called()


async def test_update_config_failure(mock_hunter_config, mock_mcp_db, mock_ctx):
    mock_hunter_config.save.side_effect = RuntimeError("permission denied")

    config_update = SearchConfigUpdate(topic="Fail")
    with pytest.raises(MCPToolError, match="permission denied"):
        await update_config(config_update, mock_ctx)
    mock_ctx.error.assert_called()


async def test_list_config_history(mock_mcp_db, mock_ctx):
    result = await list_config_history(mock_ctx)
    assert "Backup 1" in result
    mock_ctx.info.assert_called()


async def test_list_config_history_empty(mock_mcp_db, mock_ctx):
    mock_mcp_db.list_configs.return_value = []
    result = await list_config_history(mock_ctx)
    assert "No configuration history" in result
    mock_ctx.info.assert_called()


async def test_list_config_history_failure(mock_mcp_db, mock_ctx):
    mock_mcp_db.list_configs.side_effect = RuntimeError("DB error")
    with pytest.raises(MCPToolError, match="DB error"):
        await list_config_history(mock_ctx)
    mock_ctx.error.assert_called()


async def test_restore_config_by_id(mock_hunter_config, mock_mcp_db, mock_ctx):
    mock_mcp_db.get_config.return_value = {
        "settings": {"start_year": 1999},
        "anchors": {},
        "tech_strings": {},
        "tech_weights": {"old": 1.0},
        "context_rules": {},
        "keyword_only_terms": [],
        "keyword_only_category": "",
    }

    result = await restore_config_by_id(1, mock_ctx)
    assert "restored" in result.lower()
    assert mock_hunter_config.settings["start_year"] == 1999
    mock_ctx.info.assert_called()


async def test_restore_config_by_id_not_found(mock_mcp_db, mock_ctx):
    mock_mcp_db.get_config.return_value = None
    with pytest.raises(MCPToolError, match="Config ID 1 not found"):
        await restore_config_by_id(1, mock_ctx)
    mock_ctx.error.assert_called()


async def test_restore_config_by_id_failure(mock_hunter_config, mock_mcp_db, mock_ctx):
    mock_mcp_db.get_config.side_effect = RuntimeError("DB crash")
    with pytest.raises(MCPToolError, match="DB crash"):
        await restore_config_by_id(1, mock_ctx)
    mock_ctx.error.assert_called()


async def test_the_backup_does_not_store_credentials(mock_ctx, tmp_path):
    """The history is plain text in SQLite; a config backup is not a key store."""
    from academic_hunter.core.infra.config import REDACTED, HunterConfig

    secret = "s2k-must-not-reach-the-db"
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "settings": {
                    "start_year": 2021,
                    "semantic_scholar_api_key": secret,
                    "api_keys": {"semantic_scholar": secret},
                },
                "anchors": {},
                "technical_strings": {},
                "technical_weights": {},
            }
        )
    )
    real_config = HunterConfig(config_path=str(path))

    with (
        patch(
            "academic_hunter.interfaces.mcp.tools.configuration.get_config",
            return_value=real_config,
        ),
        patch(
            "academic_hunter.interfaces.mcp.tools.configuration.MCPDatabaseManager"
        ) as m_db,
    ):
        m_db.return_value.save_config.return_value = None
        await update_config(
            SearchConfigUpdate(topic="T", settings={"start_year": 2022}), mock_ctx
        )

    saved = [call.kwargs["config_data"] for call in m_db.return_value.save_config.call_args_list]
    assert saved, "nothing was backed up"
    for snapshot in saved:
        dumped = json.dumps(snapshot)
        assert secret not in dumped, f"the key reached the SQLite history: {dumped}"
        assert REDACTED in dumped, "the snapshot should still show a key is set"


@pytest.mark.parametrize(
    "field, attribute",
    [("anchors", "anchors"), ("technical_strings", "tech_strings"),
     ("technical_weights", "tech_weights")],
)
async def test_an_empty_mapping_clears_what_was_there(
    mock_hunter_config, mock_mcp_db, mock_ctx, field, attribute
):
    """`if config_update.anchors:` is falsy for `{}`.

    A researcher could replace the anchors but never remove them: the call
    reported success and the old ones stayed. An omitted field and an empty one
    are different requests — "do not touch" and "make it empty" — and only
    `is not None` can tell them apart, since the schema defaults to `None`.
    """
    setattr(mock_hunter_config, attribute, {"Old": ["term"]})

    await update_config(SearchConfigUpdate(topic="Clear", **{field: {}}), mock_ctx)

    assert getattr(mock_hunter_config, attribute) == {}, (
        f"{field} was not cleared"
    )


async def test_an_omitted_mapping_is_left_alone(mock_hunter_config, mock_mcp_db, mock_ctx):
    """The other half: not mentioning a field must not wipe it."""
    mock_hunter_config.anchors = {"Kept": ["term"]}

    await update_config(SearchConfigUpdate(topic="Only the topic"), mock_ctx)

    assert mock_hunter_config.anchors == {"Kept": ["term"]}


async def test_restoring_removes_what_was_added_after_the_backup(
    mock_hunter_config, mock_mcp_db, mock_ctx
):
    """The backup's settings were **merged** over the current ones.

    A key added after the backup survived the restore, so "restore this
    configuration" returned a hybrid of the two and the researcher could not get
    back to the state they had saved. The live credentials are the one thing that
    must survive — a backup never carries them.
    """
    mock_hunter_config.settings = {"start_year": 2024, "rerank": {"enabled": True}}
    mock_mcp_db.get_config.return_value = {"settings": {"start_year": 1999}}

    await restore_config_by_id(1, mock_ctx)

    assert mock_hunter_config.settings["start_year"] == 1999
    assert "rerank" not in mock_hunter_config.settings, (
        "a setting added after the backup survived the restore"
    )


async def _apply(config_update, mock_ctx, tmp_path, initial):
    from academic_hunter.core.infra.config import HunterConfig

    path = tmp_path / "config.json"
    path.write_text(json.dumps(initial), encoding="utf-8")

    with (
        patch(
            "academic_hunter.interfaces.mcp.tools.configuration.get_config",
            return_value=HunterConfig(config_path=str(path)),
        ),
        patch("academic_hunter.interfaces.mcp.tools.configuration.MCPDatabaseManager") as m_db,
    ):
        m_db.return_value.save_config.return_value = None
        return await update_config(config_update, mock_ctx)


async def test_update_config_names_the_sources_an_empty_technical_strings_skips(mock_ctx, tmp_path):
    """Anchors alone leave four of the six sources unqueried, and the reply said
    nothing about it.

    The call answered "successfully", the run that followed searched two sources
    of six, and the missing four reported 0 as though they had been asked and
    found nothing. Naming them here is what makes it visible before the run.
    """
    result = await _apply(
        SearchConfigUpdate(topic="CBDC", anchors={"Topic": ["central bank digital currency"]}),
        mock_ctx,
        tmp_path,
        {"settings": {}, "anchors": {}, "technical_strings": {}},
    )

    assert "successfully" in result.lower()
    assert "will NOT be queried" in result
    assert "technical_strings" in result
    for grid_source in ("ArXiv", "Crossref", "OpenAlex", "CORE"):
        assert grid_source in result, f"{grid_source} was not named as skipped"


async def test_update_config_counts_the_queries_a_complete_config_will_run(mock_ctx, tmp_path):
    """One anchor x two technical categories is two grid queries, and no warning."""
    result = await _apply(
        SearchConfigUpdate(
            topic="CBDC",
            anchors={"Topic": ["cbdc"]},
            technical_strings={"Ledger": ["distributed ledger"], "Policy": ["monetary policy"]},
        ),
        mock_ctx,
        tmp_path,
        {"settings": {}, "anchors": {}, "technical_strings": {}},
    )

    assert "2 queries" in result
    assert "will NOT be queried" not in result


async def test_update_config_says_when_the_config_will_query_nothing(mock_ctx, tmp_path):
    """Weights with no anchors are not a searchable config, and `run_search`
    would refuse. Saying so here is cheaper than the refusal later."""
    result = await _apply(
        SearchConfigUpdate(topic="CBDC", technical_weights={"iso 20022": 2.0}),
        mock_ctx,
        tmp_path,
        {"settings": {}, "anchors": {}, "technical_weights": {}},
    )

    assert "Query nothing" in result
    assert "anchors" in result


def _promised_sources(result: str) -> str:
    """The line that promises which sources the run will ask."""
    for line in result.splitlines():
        if "once per anchor x technical-string" in line:
            return line
    return ""


def _not_queried(result: str) -> str:
    """The line that names the sources this configuration cannot ask at all."""
    for line in result.splitlines():
        if "Not queried, so not a finding" in line:
            return line
    return ""


async def test_update_config_does_not_promise_a_source_that_cannot_run(mock_ctx, tmp_path, monkeypatch):
    """This reply is a promise about what the run will ask, so it has to leave
    out what the run will not ask.

    Two sources need a credential and have none here. Both are named on the
    same line, in the connector order, so the assertion is on what the line
    contains rather than on where in it a name happens to fall.
    """
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.delenv("CORE_API_KEY", raising=False)

    result = await _apply(
        SearchConfigUpdate(
            topic="CBDC",
            anchors={"Topic": ["cbdc"]},
            technical_strings={"Ledger": ["distributed ledger"]},
        ),
        mock_ctx,
        tmp_path,
        {"settings": {}, "anchors": {}, "technical_strings": {}},
    )

    promised = _promised_sources(result)
    assert promised, "the reply no longer promises anything to check against"
    assert "Semantic Scholar" not in promised
    assert "CORE" not in promised

    not_queried = _not_queried(result)
    assert "Semantic Scholar: no API key" in not_queried
    assert "CORE: no API key" in not_queried


async def test_update_config_counts_the_queries_without_pluralising_the_unit(mock_ctx, tmp_path):
    """``per anchor`` is the unit of repetition, not a count, so it stays as it
    is however many anchors there are; only the noun beside the number moves.

    Two anchors is where it shows -- "once per anchors (2 queries)" is what the
    line said, seen in a reply over the MCP, and no test pinned the count.
    """
    two = await _apply(
        SearchConfigUpdate(
            topic="CBDC",
            anchors={"Topic": ["cbdc"], "Ledger": ["distributed ledger"]},
            technical_strings={"Ledger": ["distributed ledger"]},
        ),
        mock_ctx,
        tmp_path,
        {"settings": {}, "anchors": {}, "technical_strings": {}},
    )
    promise = _promised_sources(two)
    assert "once per anchor (2 queries)" in promise
    assert "per anchors" not in promise

    one = await _apply(
        SearchConfigUpdate(
            topic="CBDC",
            anchors={"Topic": ["cbdc"]},
            technical_strings={"Ledger": ["distributed ledger"]},
        ),
        mock_ctx,
        tmp_path,
        {"settings": {}, "anchors": {}, "technical_strings": {}},
    )
    assert "once per anchor (1 query)" in _promised_sources(one)


async def test_update_config_puts_the_source_back_once_it_has_a_key(mock_ctx, tmp_path, monkeypatch):
    """The gate has to open, or "does not run without a key" is indistinguishable
    from "never runs" -- and the promise above would be wrong in the other
    direction.

    Both credentials are configured here: the assertion is that no source is
    left out, and one source left out of six would make it fail for a reason
    that has nothing to do with the gate this test is about.
    """
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "s2-test-key-do-not-use")
    monkeypatch.setenv("CORE_API_KEY", "core-test-key-do-not-use")

    result = await _apply(
        SearchConfigUpdate(
            topic="CBDC",
            anchors={"Topic": ["cbdc"]},
            technical_strings={"Ledger": ["distributed ledger"]},
        ),
        mock_ctx,
        tmp_path,
        {"settings": {}, "anchors": {}, "technical_strings": {}},
    )

    assert "Semantic Scholar" in _promised_sources(result)
    assert _not_queried(result) == ""


@pytest.fixture
def stored(monkeypatch):
    """A store that reports counts per collection, so no test opens ChromaDB."""
    from unittest.mock import MagicMock

    store = MagicMock()
    store.default_collection = "papers"
    store.collection_stats.side_effect = lambda name: {
        "count": {"papers": 1040}.get(name, 0)
    }
    monkeypatch.setattr(
        "academic_hunter.interfaces.mcp.tools.configuration._get_vector_store",
        lambda: store,
    )
    return store


def _saved(tmp_path):
    return json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))


async def test_update_config_puts_the_review_in_a_collection_of_its_own(
    mock_ctx, tmp_path, stored
):
    """Two reviews in one collection is what made every corpus analysis wrong.

    1040 papers from two searches sat in `papers`, and clustering, trends and
    duplicate detection described both while reading as statements about the
    current review.
    """
    result = await _apply(
        SearchConfigUpdate(topic="blockchain e IA", anchors={"Topic": ["blockchain"]}),
        mock_ctx,
        tmp_path,
        {"settings": {}, "anchors": {}, "technical_strings": {}},
    )

    assert "`papers` -> `review_blockchain_e_ia`" in result
    assert "1040 papers stay in `papers` and are not moved" in result
    assert _saved(tmp_path)["settings"]["collection_name"] == "review_blockchain_e_ia"


async def test_a_later_tweak_does_not_move_an_established_review(
    mock_ctx, tmp_path, stored
):
    """The regression that matters most here.

    An agent that calls `update_config` to change a threshold names no topic. If
    that derived a fresh name from the anchors, the next run would index into a
    new collection while the review's own corpus sat in the old one, unread —
    silently, and looking like an empty review.
    """
    initial = {
        "settings": {"collection_name": "review_blockchain_e_ia", "min_relevance_score": 5.0},
        "anchors": {"Topic": ["blockchain"]},
        "technical_strings": {"Model": ["transformer"]},
    }

    result = await _apply(
        SearchConfigUpdate(settings={"min_relevance_score": 6.0}),
        mock_ctx,
        tmp_path,
        initial,
    )

    assert _saved(tmp_path)["settings"]["collection_name"] == "review_blockchain_e_ia"
    assert "->" not in result.split("Collection:")[-1]


async def test_an_unnamed_review_gets_a_collection_from_its_anchors(
    mock_ctx, tmp_path, stored
):
    """The one case the anchors are for: a config still on the shared collection.

    Deriving here names the review without moving anything, because nothing has
    been indexed for it yet — its papers are in `papers` only by accident of
    there being nowhere else to put them.
    """
    result = await _apply(
        SearchConfigUpdate(anchors={"Topic": ["cbdc"], "Tech": ["distributed ledger"]}),
        mock_ctx,
        tmp_path,
        {"settings": {}, "anchors": {}, "technical_strings": {}},
    )

    assert "-> `review_cbdc_distributed_ledger`" in result
    assert _saved(tmp_path)["settings"]["collection_name"] == "review_cbdc_distributed_ledger"


async def test_an_explicit_collection_name_is_kept(mock_ctx, tmp_path, stored):
    result = await _apply(
        SearchConfigUpdate(topic="ignored", settings={"collection_name": "my_own_review"}),
        mock_ctx,
        tmp_path,
        {"settings": {}, "anchors": {}, "technical_strings": {}},
    )

    assert _saved(tmp_path)["settings"]["collection_name"] == "my_own_review"
    assert "my_own_review" in result


async def test_a_collection_name_chromadb_would_reject_is_refused(
    mock_ctx, tmp_path, stored
):
    """Refused, not quietly replaced: the operator named it, and the point of the
    reply is to say which collection holds the papers."""
    with pytest.raises(MCPToolError, match="not a name ChromaDB accepts"):
        await _apply(
            SearchConfigUpdate(topic="x", settings={"collection_name": "Bad Name!"}),
            mock_ctx,
            tmp_path,
            {"settings": {}, "anchors": {}, "technical_strings": {}},
        )


async def test_a_topic_that_slugs_to_nothing_leaves_the_name_alone(
    mock_ctx, tmp_path, stored
):
    """A topic of punctuation has no legal name in it, and guessing one would be
    worse than keeping what is there."""
    result = await _apply(
        SearchConfigUpdate(topic="???"),
        mock_ctx,
        tmp_path,
        {"settings": {}, "anchors": {}, "technical_strings": {}},
    )

    assert "Collection: `papers` (unchanged)" in result
    assert "collection_name" not in _saved(tmp_path)["settings"]


async def test_read_config_says_which_file_it_read(mock_ctx, tmp_path, monkeypatch):
    """The search order is environment-dependent, so the caller has to be told
    which rung won — otherwise "my config is being ignored" has no answer, and
    the packaged default looks like a config someone chose, only an empty one."""
    from academic_hunter.core.infra import paths
    from academic_hunter.core.infra.config import HunterConfig

    target = tmp_path / paths.CONFIG_FILENAME
    target.write_text(
        json.dumps({"settings": {"start_year": 2016}, "anchors": {"T": ["x"]}}),
        encoding="utf-8",
    )
    monkeypatch.setenv(paths.CONFIG_ENV, str(target))

    with patch(
        "academic_hunter.interfaces.mcp.tools.configuration.get_config",
        side_effect=HunterConfig,
    ):
        data = json.loads(await read_config(mock_ctx))

    assert data["config_source"]["path"] == str(target)
    assert data["config_source"]["origin"] == paths.ORIGIN_ENV
    assert data["config_source"]["is_default"] is False
    assert data["settings"]["start_year"] == 2016


async def test_read_config_flags_the_packaged_default(mock_ctx, tmp_path, monkeypatch):
    from academic_hunter.core.infra import paths
    from academic_hunter.core.infra.config import HunterConfig

    monkeypatch.setattr(paths, "checkout_root", lambda: None)
    for name in (paths.CONFIG_ENV, paths.DATA_ENV, paths.PROJECT_ENV):
        monkeypatch.delenv(name, raising=False)
    neutral = tmp_path / "neutral"
    neutral.mkdir()
    monkeypatch.chdir(neutral)

    with patch(
        "academic_hunter.interfaces.mcp.tools.configuration.get_config",
        side_effect=HunterConfig,
    ):
        data = json.loads(await read_config(mock_ctx))

    assert data["config_source"]["is_default"] is True
    assert data["config_source"]["origin"] == paths.ORIGIN_PACKAGED


async def test_read_config_names_a_cut_that_cannot_exclude_anything(mock_ctx, tmp_path, monkeypatch):
    """A leitura tem de dizer o mesmo que a escrita, senão o aviso é de quem grava.

    ``_config_notes`` era renderizado só por ``_search_plan``, chamado de um
    único sítio: dentro do ``update_config``. Uma configuração inerte -- todas as
    âncoras ao peso do corte -- avisava quem a escrevia e ficava muda para quem
    apenas a lia, que é o caso de todo o agente a retomar um trabalho. O
    ``config.json`` dos microplásticos é exactamente esta configuração, e lia-se
    sem uma palavra.
    """
    from academic_hunter.core.infra import paths
    from academic_hunter.core.infra.config import HunterConfig

    target = tmp_path / paths.CONFIG_FILENAME
    target.write_text(
        json.dumps(
            {
                "settings": {
                    "min_inclusion_score": 5,
                    "context_rules": {"microplastics": ["water"]},
                },
                "anchors": {"Plastics": ["microplastics"]},
                "technical_weights": {"microplastics": 5.0},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(paths.CONFIG_ENV, str(target))

    with patch(
        "academic_hunter.interfaces.mcp.tools.configuration.get_config",
        side_effect=HunterConfig,
    ):
        data = json.loads(await read_config(mock_ctx))

    assert any("Excludes nothing" in note for note in data["notes"]), data["notes"]


async def test_read_config_says_nothing_when_the_cut_still_excludes(mock_ctx, tmp_path, monkeypatch):
    """A chave existe sempre, e vazia -- "nada encontrado" não é "nada procurado"."""
    from academic_hunter.core.infra import paths
    from academic_hunter.core.infra.config import HunterConfig

    target = tmp_path / paths.CONFIG_FILENAME
    target.write_text(
        json.dumps(
            {
                "settings": {"min_inclusion_score": 5},
                "anchors": {"Topic": ["blockchain"]},
                "technical_weights": {"blockchain": 2.0},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(paths.CONFIG_ENV, str(target))

    with patch(
        "academic_hunter.interfaces.mcp.tools.configuration.get_config",
        side_effect=HunterConfig,
    ):
        data = json.loads(await read_config(mock_ctx))

    assert data["notes"] == [], data["notes"]


def _summary(tmp_path, **raw):
    """``_ranking_summary`` over a configuration written to a throwaway file."""
    from academic_hunter.core.infra.config import HunterConfig
    from academic_hunter.interfaces.mcp.tools.configuration import _ranking_summary

    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return _ranking_summary(HunterConfig(config_path=str(path)))


def test_the_ranking_says_what_orders_the_papers_when_no_query_is_set(tmp_path):
    """Empty ``ranking_query`` is the shipped default, and it was silent.

    With no query the ordering is ``_kw_score`` -- a function of the paper and of
    the configured terms, which never sees what is being looked for, and so is
    the same ordering whatever the research question is. Measured on a hand-judged
    blockchain pool (5 queries, 250 graded judgments): nDCG@10 0.25 by that score,
    against 0.67 for BM25 over a question. The template ships the query empty, so
    this is what a new configuration gets.
    """
    text = _summary(
        tmp_path,
        settings={"min_inclusion_score": 5},
        anchors={"Plastics": ["microplastics"]},
        technical_weights={"microplastics": 5.0},
    )

    assert "keyword score" in text, text
    assert "0.25" in text, f"the measurement is missing: {text}"
    assert "ranking_query" in text, f"the remedy is missing: {text}"


def test_the_ranking_says_the_query_when_one_is_set(tmp_path):
    """The other mode, and the one the template's 0.67 belongs to."""
    text = _summary(
        tmp_path,
        settings={"min_inclusion_score": 5, "ranking_query": "How do microplastics move?"},
        anchors={"Plastics": ["microplastics"]},
        technical_weights={"microplastics": 5.0},
    )

    assert "How do microplastics move?" in text, text
    assert "keyword score" in text, text


def test_an_empty_query_does_not_turn_into_a_note(tmp_path):
    """It is a description, not a defect, and ``notes`` has to stay able to be empty.

    A note here would fire for every configuration the shipped template produces,
    and a report that always has something in it is one the reader learns to skip
    -- which is what ``test_notes_are_silent_about_a_configuration_with_nothing_wrong``
    exists to protect.
    """
    notes = _notes(
        tmp_path,
        settings={
            "min_inclusion_score": 5,
            "title_multiplier": 1.5,
            "context_rules": {"cbdc": ["central bank", "monetary authority"]},
        },
        anchors={"Topic": ["cbdc"]},
        technical_strings={"Ledger": ["distributed ledger"]},
        technical_weights={"distributed ledger": 3.0},
    )

    assert notes == [], notes


def test_the_plan_says_what_ranks_the_papers_when_no_query_is_set(tmp_path):
    """``update_config`` says the same thing as it writes the configuration."""
    plan = _plan(
        tmp_path,
        set(),
        settings={"min_inclusion_score": 5},
        anchors={"Plastics": ["microplastics"]},
        technical_strings={"Core": ["microplastics"]},
        technical_weights={"microplastics": 5.0},
    )

    line = _note(plan, "Rank every paper by the keyword score")
    assert "0.25" in line, line


def _notes(tmp_path, **raw):
    """``_config_notes`` over a configuration written to a throwaway file."""
    from academic_hunter.core.infra.config import HunterConfig
    from academic_hunter.interfaces.mcp.tools.configuration import _config_notes

    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return _config_notes(HunterConfig(config_path=str(path)))


def _notes_with_sent(tmp_path, sent, **raw):
    """``_config_notes`` told which ``settings`` keys the caller passed."""
    from academic_hunter.core.infra.config import HunterConfig
    from academic_hunter.interfaces.mcp.tools.configuration import _config_notes

    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return _config_notes(HunterConfig(config_path=str(path)), sent)


def _note(result, needle):
    """The report line containing ``needle``, or a failure that prints the reply."""
    for line in result.splitlines():
        if needle in line:
            return line
    raise AssertionError(f"no line of the reply mentions {needle!r}:\n{result}")


def _plan(tmp_path, sent, **raw):
    """``_search_plan`` over a configuration written to a throwaway file."""
    from academic_hunter.core.infra.config import HunterConfig
    from academic_hunter.interfaces.mcp.tools.configuration import _search_plan

    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return _search_plan(HunterConfig(config_path=str(path)), sent)


def test_the_plan_names_what_ranks_the_papers_and_what_dates_them(tmp_path):
    """The two settings that shape a run without being a term, said out loud.

    Neither appeared anywhere in this reply before, and both decide the corpus:
    ``ranking_query`` replaces the keyword score as the ordering of every paper,
    and ``start_year`` removes papers before the gate ever sees them. Measured on
    a real run, a Stellar review came out ordered end to end by the previous
    topic's question about quantisation, and only the CSV's ``_bm25_score``
    column said so.
    """
    plan = _plan(
        tmp_path,
        {"ranking_query", "start_year"},
        settings={
            "ranking_query": "How does the Stellar consensus protocol reach agreement?",
            "start_year": 2022,
            "min_inclusion_score": 5,
        },
        anchors={"Stellar": ["stellar"]},
        technical_strings={"Consensus": ["quorum"]},
        technical_weights={"stellar": 5.0},
    )

    assert "How does the Stellar consensus protocol reach agreement?" in _note(
        plan, "Rank every paper by BM25"
    )
    assert "Keep only papers published from 2022 on" in plan
    assert "`_kw_score >= 5`" in plan


def test_notes_name_the_settings_the_call_did_not_send(tmp_path):
    """``settings`` is merged, so an omitted key keeps the last topic's value.

    This is the shape of the failure that motivated the line: an agent sends
    anchors and technical terms for a new topic, says nothing about ``settings``,
    and inherits a ranking question from the topic before it. The write succeeds
    and the reply is confident, because nothing that ran was wrong -- only the
    order of everything.
    """
    notes = _notes_with_sent(
        tmp_path,
        {"anchors", "technical_strings"},
        settings={"ranking_query": "quantization at inference time", "start_year": 2022},
        anchors={"Topic": ["stellar"]},
        technical_weights={"stellar": 5.0},
    )

    line = _note("\n".join(notes), "Not sent by this call, so kept")
    assert "`ranking_query`" in line
    assert "`start_year`" in line
    assert "merged, not replaced" in line


def test_notes_stay_silent_when_the_call_sent_those_settings(tmp_path):
    """A line that speaks when there is nothing to report teaches the agent to
    skip the report, so the check is on what was sent, not on what is set."""
    notes = _notes_with_sent(
        tmp_path,
        {"ranking_query", "start_year"},
        settings={"ranking_query": "quantization at inference time", "start_year": 2022},
        anchors={"Topic": ["stellar"]},
        technical_weights={"stellar": 5.0},
    )

    assert "Not sent by this call" not in "\n".join(notes)


def test_notes_claim_nothing_when_the_caller_does_not_say_what_it_sent(tmp_path):
    """``sent=None`` means unknown, and unknown is not inherited."""
    notes = _notes(
        tmp_path,
        settings={"ranking_query": "quantization at inference time"},
        anchors={"Topic": ["stellar"]},
        technical_weights={"stellar": 5.0},
    )

    assert "Not sent by this call" not in "\n".join(notes)


def test_notes_leave_the_citation_count_as_the_whole_score(tmp_path):
    """Anchors with an empty weight map pass every guard and score nothing.

    ``is_scorable`` asks only for anchors, so this configuration issues every
    query, admits every paper through the gate, and then scores each of them on
    ``log10(citations + 1)`` alone. The figure matters: it is why the run comes
    back nearly empty, and it is not a number anyone would guess.
    """
    notes = _notes(
        tmp_path,
        settings={"min_inclusion_score": 5},
        anchors={"Topic": ["llm"]},
        technical_weights={},
    )

    line = _note("\n".join(notes), "log10(citations + 1)")
    assert "99,999" in line


def test_notes_do_not_read_a_low_weight_as_no_weight(tmp_path):
    """A weight of 0.5 scores. An empty map does not, and only one of the two
    leaves the score to the citation count -- which is why the two cases are
    reported apart rather than as one "weak weights" line."""
    notes = _notes(
        tmp_path,
        settings={"min_inclusion_score": 5},
        anchors={"Topic": ["llm"]},
        technical_weights={"llm": 0.5},
    )

    assert not any("log10(citations + 1)" in line for line in notes)


def test_notes_name_an_anchor_whose_weight_admits_on_its_own(tmp_path):
    """The measured admission vector, and the check that obvious ones miss.

    `llm` is not a generic word, and the configuration that failed had two
    anchor groups, so neither "generic term" nor "one group" catches this. What
    catches it is that the term is an anchor *and* carries a weight that clears
    the cut on a title hit, with no context rule to hold it back: the gate takes
    the paper and nothing else has to be true of it.
    """
    notes = _notes(
        tmp_path,
        settings={"min_inclusion_score": 5, "title_multiplier": 1.5},
        anchors={"Models": ["llm", "transformer"]},
        technical_weights={"llm": 5.0, "transformer": 5.0},
    )

    line = _note("\n".join(notes), "Admits anything")
    assert "llm (5)" in line
    assert "transformer (5)" in line


def test_notes_leave_a_guarded_anchor_alone(tmp_path):
    """A context rule is the whole remedy, so a term that has one is not named.

    Silencing ``Admits anything`` is all this rule buys: the rule constrains
    which papers pass the gate, but every one that passes still has the term
    counted, so the cut here removes nothing. ``Excludes nothing`` says that,
    and it is a different claim about a different set of papers.
    """
    notes = _notes(
        tmp_path,
        settings={"min_inclusion_score": 5, "context_rules": {"llm": ["language model"]}},
        anchors={"Models": ["llm"]},
        technical_weights={"llm": 5.0},
    )

    assert not any("Admits anything" in line for line in notes)


def test_notes_name_a_cut_that_cannot_exclude_anything(tmp_path):
    """O defeito medido: todas as âncoras pesam exactamente o corte.

    O gate só admite um paper que contenha um termo-âncora, e todas as âncoras
    levam o peso do próprio corte — logo todo o paper admitido já pontua no corte
    antes de mais nada ser verdade sobre ele. Medido: ``evaluated: 252,
    included: 252, excluded: 0``.

    As âncoras aqui têm todas regra de contexto, e é por isso que a verificação
    antiga ficou calada: ``Admits anything`` exige que a regra esteja ausente.
    """
    notes = _notes(
        tmp_path,
        settings={
            "min_inclusion_score": 5,
            "context_rules": {"microplastics": ["water"], "nanoplastics": ["water"]},
        },
        anchors={"Plastics": ["microplastics", "nanoplastics"]},
        technical_weights={"microplastics": 5.0, "nanoplastics": 5.0},
    )

    _note("\n".join(notes), "Excludes nothing")
    assert not any("Admits anything" in note for note in notes)


def test_an_anchor_under_the_cut_leaves_the_cut_working(tmp_path):
    """Uma âncora abaixo do corte chega: os papers que ela admite podem cair."""
    notes = _notes(
        tmp_path,
        settings={"min_inclusion_score": 5},
        anchors={"Topic": ["blockchain", "ledger"]},
        technical_weights={"blockchain": 5.0, "ledger": 2.0},
    )

    assert not any("Excludes nothing" in note for note in notes)


def test_an_anchor_with_no_weight_at_all_leaves_the_cut_working(tmp_path):
    """Uma âncora sem peso admite um paper que só pontua ``log10(citações + 1)``."""
    notes = _notes(
        tmp_path,
        settings={"min_inclusion_score": 5},
        anchors={"Topic": ["blockchain", "ledger"]},
        technical_weights={"blockchain": 5.0},
    )

    assert not any("Excludes nothing" in note for note in notes)


def test_a_weight_that_is_not_a_number_is_not_called_an_inert_cut(tmp_path):
    """``Score nothing`` já é dono dessa configuração; dizer inerte seria adivinhar."""
    notes = _notes(
        tmp_path,
        settings={"min_inclusion_score": 5},
        anchors={"Topic": ["blockchain"]},
        technical_weights={"blockchain": "high"},
    )

    assert not any("Excludes nothing" in note for note in notes)


def test_a_cut_above_the_lightest_anchor_is_left_alone(tmp_path):
    notes = _notes(
        tmp_path,
        settings={"min_inclusion_score": 6},
        anchors={"Topic": ["blockchain", "ledger"]},
        technical_weights={"blockchain": 5.0, "ledger": 5.0},
    )

    assert not any("Excludes nothing" in note for note in notes)


def test_the_real_configuration_that_failed_is_not_called_inert(tmp_path):
    """Três das suas âncoras não têm peso, logo lá o corte remove papers."""
    notes = _notes(tmp_path, **_LOW_LEVEL_AI)

    assert not any("Excludes nothing" in note for note in notes)


def test_the_line_quotes_the_cut_and_the_lightest_anchor(tmp_path):
    """Os dois números da aritmética, para o leitor poder conferi-la."""
    notes = _notes(
        tmp_path,
        settings={"min_inclusion_score": 5},
        anchors={"Topic": ["blockchain"]},
        technical_weights={"blockchain": 6.0},
    )

    line = _note("\n".join(notes), "Excludes nothing")
    assert "cut is 5" in line
    assert "weighs 6" in line
    assert "above the lightest anchor's weight" in line


def test_an_unguarded_anchor_reads_as_both_cause_and_detail(tmp_path):
    """Sem regras as duas linhas disparam, e não são a mesma afirmação.

    ``Admits anything`` nomeia os termos que uma query admite sozinhos; esta diz
    que o corte não remove nada de todo o conjunto admitido, o que é verdade
    independentemente das regras. Ler as duas seguidas lê-se como causa e
    detalhe.
    """
    notes = _notes(
        tmp_path,
        settings={"min_inclusion_score": 5},
        anchors={"Topic": ["blockchain"]},
        technical_weights={"blockchain": 5.0},
    )

    joined = "\n".join(notes)
    assert "Admits anything" in joined
    assert "Excludes nothing" in joined


def test_notes_name_a_context_rule_that_can_never_fire(tmp_path):
    """A rule is looked up by the anchor term that matched, lower-cased.

    On the config that failed, three rules were keyed on terms that are weights
    and not anchors -- so nothing ever read them, and the terms they were
    written to constrain passed unchallenged. It is not a weak filter; it is no
    filter, and it was silent.
    """
    notes = _notes(
        tmp_path,
        settings={
            "min_inclusion_score": 5,
            "context_rules": {"pruning": ["neural network"], "llm": ["language model"]},
        },
        anchors={"Models": ["llm"]},
        technical_weights={"llm": 5.0, "pruning": 3.0},
    )

    line = _note("\n".join(notes), "Never fire")
    assert "pruning" in line
    assert "llm" not in line


def test_notes_name_a_weight_no_context_rule_can_reach(tmp_path):
    """The other direction of the same asymmetry, with a different remedy.

    A rule cannot be written for a term that is not an anchor, so the only fix
    is to make it one -- or to stop weighting it.
    """
    notes = _notes(
        tmp_path,
        settings={"min_inclusion_score": 5, "title_multiplier": 1.5},
        anchors={"Models": ["llm"]},
        technical_weights={"llm": 5.0, "cuda kernel": 5.0, "latency": 1.5},
    )

    line = _note("\n".join(notes), "Score without a guard")
    assert "cuda kernel (5)" in line
    assert "latency (1.5)" not in line, "1.5 x 1.5 is 2.25 and does not clear 5"


def test_notes_name_the_two_ways_technical_strings_and_weights_disagree(tmp_path):
    """One list is queried and the other is scored, and neither implies the other.

    A term in `technical_strings` with no weight is asked for, printed in
    Tech_Terms, and counted for nothing; a weight outside both lists and the
    anchors is scored but never searched for.
    """
    notes = _notes(
        tmp_path,
        settings={"min_inclusion_score": 5},
        anchors={"Models": ["llm"]},
        technical_strings={"Hardware": ["gpu", "tpu"]},
        technical_weights={"llm": 5.0, "gpu": 3.0, "case study": 1.5},
    )
    result = "\n".join(notes)

    assert "tpu" in _note(result, "Queried but never scored")
    assert "gpu" not in _note(result, "Queried but never scored")
    assert "case study" in _note(result, "Weighted but never queried")


def test_notes_name_a_generic_term_in_use(tmp_path):
    """Frequency cannot separate a field's vocabulary from every field's.

    Measured on the delivered run, `framework` matched 316 of 1151 papers and
    `accuracy` 424 -- more than the topic's own core term, `quantization` at
    464. The counts are the evidence; naming them here is what makes a term
    that means anything an anchor, and a term that means nothing unweighted.
    """
    notes = _notes(
        tmp_path,
        settings={"min_inclusion_score": 5},
        anchors={"Models": ["llm"]},
        technical_strings={"Evaluation": ["framework", "perplexity"]},
        technical_weights={"llm": 5.0, "framework": 1.5, "perplexity": 3.0},
    )

    line = _note("\n".join(notes), "Generic terms in use")
    assert "framework" in line
    assert "perplexity" not in line


def test_notes_name_a_generic_anchor_that_carries_no_weight(tmp_path):
    """The one shape that passed every check: generic, an anchor, and unweighted.

    A weight is what makes "Admits anything" fire, and membership of
    ``technical_strings`` is what puts a term in the generic list, so a term that
    is neither slips past both -- found by driving a one-group draft through the
    MCP, whose anchors were `llm, transformer, model, large language model` and
    whose reply named only the four generic terms of `technical_strings`. It is
    not harmless: the anchor side of every query is built from the anchors, so
    the word is asked for, and the gate admits any paper that uses it.
    """
    notes = _notes(
        tmp_path,
        settings={"min_inclusion_score": 5},
        anchors={"Models": ["llm", "model"]},
        technical_strings={"Evaluation": ["perplexity"]},
        technical_weights={"llm": 5.0, "perplexity": 3.0},
    )
    result = "\n".join(notes)

    line = _note(result, "Generic terms in use")
    assert "model" in line
    assert "model appears among the anchors as well" in line
    assert "llm" not in line, "a term the field owns was called generic"

    admits = _note(result, "Admits anything")
    assert "model" not in admits, "the fixture no longer isolates the unweighted case"


def test_notes_name_a_weight_that_is_not_a_number(tmp_path):
    """A string weight does not fail loudly anywhere near where it is written.

    It raises inside `calculate_score` on the first paper, the worker catches it
    per paper and logs "dropped one paper", and the run finishes with an empty
    corpus and no reason given.
    """
    notes = _notes(
        tmp_path,
        settings={"min_inclusion_score": 5},
        anchors={"Models": ["llm"]},
        technical_weights={"llm": 5.0, "quantization": "high"},
    )

    line = _note("\n".join(notes), "cannot be multiplied")
    assert "quantization" in line


def test_notes_are_silent_about_a_configuration_with_nothing_wrong(tmp_path):
    """The report has to be able to say nothing, or it teaches the reader to
    skip it -- and the check that always fires is the one that hides the rest.

    A guarded anchor, a weight low enough not to decide anything on its own, and
    the two lists agreeing: nothing here is a defect.
    """
    notes = _notes(
        tmp_path,
        settings={
            "min_inclusion_score": 5,
            "title_multiplier": 1.5,
            "context_rules": {"cbdc": ["central bank", "monetary authority"]},
        },
        anchors={"Topic": ["cbdc"]},
        technical_strings={"Ledger": ["distributed ledger"]},
        technical_weights={"distributed ledger": 3.0},
    )

    assert notes == []


_LOW_LEVEL_AI = {
    "settings": {
        "min_inclusion_score": 5,
        "min_relevance_score": 5,
        "title_multiplier": 1.5,
        "score_precision": 1,
    },
    "context_rules": {
        "quantization": [
            "neural network", "neural networks", "deep learning",
            "large language model", "llm", "transformer", "model compression",
        ],
        "inference": [
            "neural network", "neural networks", "large language model",
            "llm", "deep learning", "transformer",
        ],
        "pruning": [
            "neural network", "neural networks", "deep learning",
            "model compression", "sparsity", "llm",
        ],
        "distillation": [
            "knowledge distillation", "neural network", "neural networks",
            "teacher", "student", "model compression",
        ],
        "kernel": ["gpu", "cuda", "neural network", "tensor", "hardware", "llm"],
        "transformer": [
            "attention", "language model", "neural network", "llm", "deep learning",
        ],
    },
    "anchors": {
        "Language_Models": [
            "large language model", "llm", "language model", "transformer",
            "foundation model",
        ],
        "Inference_Efficiency": [
            "inference", "quantization", "model compression", "acceleration",
            "efficient inference",
        ],
    },
    "technical_strings": {
        "Quantization": [
            "quantization", "low-bit", "int8", "4-bit", "mixed-precision",
            "post-training quantization", "quantization-aware training",
            "weight-only quantization", "activation quantization", "vector quantization",
        ],
        "Kernels_And_Operators": [
            "kernel", "cuda", "triton", "flash attention", "paged attention",
            "operator fusion", "tiling", "memory bandwidth", "roofline",
        ],
        "Hardware_And_Accelerators": [
            "accelerator", "gpu", "tpu", "tensor core", "hardware co-design",
            "on-device", "fpga", "asic",
        ],
        "Serving_And_Memory": [
            "kv cache", "batching", "throughput", "latency", "serving",
            "speculative decoding", "pruning", "knowledge distillation",
            "sparsity", "memory footprint",
        ],
        "Evaluation": [
            "benchmark", "perplexity", "accuracy", "energy efficiency",
            "scalability", "survey", "taxonomy", "framework",
        ],
    },
    "technical_weights": {
        "large language model": 5, "llm": 5, "quantization": 5, "low-bit": 5,
        "kv cache": 5, "flash attention": 5, "paged attention": 5,
        "mixed-precision": 5, "post-training quantization": 5,
        "weight-only quantization": 5, "transformer": 5,
        "inference": 3, "inference engine": 3, "speculative decoding": 3,
        "operator fusion": 3, "tensor core": 3, "hardware co-design": 3,
        "cuda kernel": 3, "roofline": 3, "memory bandwidth": 3, "pruning": 3,
        "knowledge distillation": 3, "sparsity": 3, "accelerator": 3,
        "on-device": 3, "serving": 3, "throughput": 3,
        "quantization-aware training": 3, "energy efficiency": 3,
        "model compression": 3, "activation quantization": 3,
        "vector quantization": 3, "int8": 3, "4-bit": 3,
        "latency": 1.5, "perplexity": 1.5, "benchmark": 1.5, "framework": 1.5,
        "architecture": 1.5, "survey": 1.5, "taxonomy": 1.5, "scalability": 1.5,
        "case study": 1.5,
    },
}
"""The configuration behind ``results/run_20261007_193626``, which failed.

1151 papers included, of which roughly 92 in a hundred were inside the topic;
`llm` alone admitted 513 of them through an unguarded anchor, and 997 were
dropped at the gate. It is pinned here because ``config.json`` is not in the
repository and that run will not be repeated: this is what makes "the reply
names the defects" checkable against the configuration that had them.
"""


async def test_update_config_names_the_defects_of_the_configuration_that_failed(
    mock_ctx, tmp_path
):
    """The strongest and cheapest proof of the second half of the goal.

    Every line asserted here is a fact about a real corpus, and every one of
    them passed in silence when this configuration was written. The point is not
    that the reply changes the config -- it does not -- but that a defect cannot
    be written without being named.
    """
    result = await _apply(
        SearchConfigUpdate(
            topic="Low Level AI",
            settings=_LOW_LEVEL_AI["settings"],
            anchors=_LOW_LEVEL_AI["anchors"],
            technical_strings=_LOW_LEVEL_AI["technical_strings"],
            technical_weights=_LOW_LEVEL_AI["technical_weights"],
            context_rules=_LOW_LEVEL_AI["context_rules"],
        ),
        mock_ctx,
        tmp_path,
        {"settings": {}, "anchors": {}, "technical_strings": {}},
    )

    assert "What this configuration will fail to do:" in result

    admits = _note(result, "Admits anything")
    assert "llm (5)" in admits
    assert "large language model (5)" in admits
    assert "transformer" not in admits, "its context rule keeps it out of this line"

    unguarded = _note(result, "Score without a guard")
    for term in ("kv cache", "flash attention", "weight-only quantization"):
        assert term in unguarded
    named = unguarded.split(": ", 1)[1].split(" -- ", 1)[0]
    terms = [item.rsplit(" (", 1)[0] for item in named.split(", ")]
    assert "quantization" not in terms, "its context rule keeps it out"
    assert "inference" not in terms, "its context rule keeps it out"

    dead = _note(result, "Never fire")
    for key in ("pruning", "distillation", "kernel"):
        assert key in dead

    generic = _note(result, "Generic terms in use")
    for term in ("framework", "survey", "accuracy", "taxonomy", "benchmark"):
        assert term in generic

    unscored = _note(result, "Queried but never scored")
    for term in ("gpu", "cuda", "tpu", "fpga", "asic"):
        assert term in unscored

    unqueried = _note(result, "Weighted but never queried")
    for term in ("inference engine", "cuda kernel", "architecture", "case study"):
        assert term in unqueried


async def test_update_config_says_nothing_extra_about_a_sound_configuration(
    mock_ctx, tmp_path
):
    """The other half of the contract: a reply that always warns is not read."""
    result = await _apply(
        SearchConfigUpdate(
            topic="CBDC",
            settings={
                "min_inclusion_score": 5,
                "context_rules": {"cbdc": ["central bank", "monetary authority"]},
            },
            anchors={"Topic": ["cbdc"]},
            technical_strings={"Ledger": ["distributed ledger"]},
            technical_weights={"distributed ledger": 3.0},
        ),
        mock_ctx,
        tmp_path,
        {"settings": {}, "anchors": {}, "technical_strings": {}},
    )

    assert "will fail to do" not in result


_ASTRO_TITLES = [
    "Stellar populations in the Local Group",
    "MESA isochrones and stellar evolution",
    "Stellar winds from massive stars",
    "Metallicity gradients in stellar clusters",
    "Asteroseismology of stellar interiors",
]

_STELLAR_BLOCKCHAIN = {
    "Stellar": ["stellar", "soroban", "stellar network", "stellar blockchain", "lumens"],
}


def _discovered(topic, titles):
    """Seed what a discovery for ``topic`` would have left behind."""
    from academic_hunter.interfaces.mcp.cache import discovery_titles
    from academic_hunter.interfaces.mcp.tools.discovery import _candidate_terms

    discovery_titles.set(
        topic,
        {"topic": topic, "titles": titles, "candidates": _candidate_terms(titles)},
    )


def _against_discovery(tmp_path, topic, **anchors):
    """``_discovery_note`` over a configuration written to a throwaway file."""
    from academic_hunter.core.infra.config import HunterConfig
    from academic_hunter.interfaces.mcp.tools.configuration import _discovery_note

    path = tmp_path / "config.json"
    path.write_text(json.dumps({"anchors": anchors}), encoding="utf-8")
    return _discovery_note(HunterConfig(config_path=str(path)), topic)


def test_a_discovery_of_another_field_is_named_against_the_anchors(tmp_path):
    """The measured failure, and why the check counts a group rather than a term.

    Run for real, "Stellar" returned stellar populations and MESA isochrones,
    and the blockchain configuration was written over it unchanged. `stellar`
    itself was the one anchor that matched -- so a check asking whether any
    anchor appears would have found it and stayed quiet.
    """
    _discovered("Stellar", _ASTRO_TITLES)

    lines = _against_discovery(tmp_path, "Stellar", **_STELLAR_BLOCKCHAIN)

    assert len(lines) == 1
    note = lines[0]
    for absent in ("soroban", "stellar network", "stellar blockchain", "lumens"):
        assert absent in note
    assert "4 of the 5" in note
    assert "stellar, in 5" in note
    assert "stellar populations" in note


def test_anchors_the_discovery_does_use_stay_silent(tmp_path):
    _discovered("Stellar", _ASTRO_TITLES)

    assert _against_discovery(tmp_path, "Stellar", Astro=["stellar", "metallicity"]) == []


def test_the_trigger_wants_a_majority_of_the_group(tmp_path):
    """One absent term is ordinary -- a rare synonym beside a common one says
    nothing is wrong. A group mostly absent is a group that cannot gate much.
    """
    _discovered("Stellar", _ASTRO_TITLES)

    assert _against_discovery(tmp_path, "Stellar", G=["stellar", "soroban"]) == []
    assert _against_discovery(tmp_path, "Stellar", G=["soroban", "lumens"])


def test_a_differently_written_topic_still_finds_its_discovery(tmp_path):
    """The topic is typed once into the discovery and again here, by hand."""
    _discovered("Stellar", _ASTRO_TITLES)

    assert _against_discovery(tmp_path, "  stellar ", **_STELLAR_BLOCKCHAIN)


def test_nothing_is_claimed_when_no_discovery_ran(tmp_path):
    assert _against_discovery(tmp_path, "Stellar", **_STELLAR_BLOCKCHAIN) == []


def test_a_topic_that_was_never_discovered_is_named_rather_than_checked(tmp_path):
    """Two records and no match: naming them is the whole of what is known."""
    _discovered("Genre Analysis", _ASTRO_TITLES)
    _discovered("CBDC", _ASTRO_TITLES)

    lines = _against_discovery(tmp_path, "Stellar", **_STELLAR_BLOCKCHAIN)

    assert len(lines) == 1
    assert "Genre Analysis" in lines[0] and "CBDC" in lines[0]
    assert "Stellar" in lines[0]
    assert "soroban" not in lines[0]


def test_a_group_that_is_not_a_list_is_survived(tmp_path):
    """A group written as a bare string would otherwise be iterated by letter."""
    _discovered("Stellar", _ASTRO_TITLES)

    assert isinstance(_against_discovery(tmp_path, "Stellar", G="stellar"), list)
    assert isinstance(_against_discovery(tmp_path, "Stellar", G=None), list)


def test_an_uppercase_title_still_counts_as_a_hit(tmp_path):
    """The pipeline lowercases the text before matching, and so must this.

    Forget it and every count is zero, which turns the note into an alarm on
    every configuration ever written.
    """
    _discovered("Stellar", ["SOROBAN CONTRACTS ON THE STELLAR NETWORK"])

    assert _against_discovery(tmp_path, "Stellar", G=["stellar network", "soroban"]) == []


async def test_update_config_reports_the_discovery_of_another_field(mock_ctx, tmp_path):
    _discovered("Stellar", _ASTRO_TITLES)

    result = await _apply(
        SearchConfigUpdate(topic="Stellar", anchors=_STELLAR_BLOCKCHAIN),
        mock_ctx,
        tmp_path,
        {"settings": {}, "anchors": {}, "technical_strings": {}},
    )

    assert "successfully" in result
    assert "quick_topic_discovery returned" in result
    assert "soroban" in result
