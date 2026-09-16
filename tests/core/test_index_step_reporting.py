"""Uma indexação que falha não pode ser silenciosa.

`index_papers` devolve um booleano, e o passo usava os dois ramos de forma
assimétrica: o sucesso registrava uma linha, a falha não fazia nada. Um run cuja
indexação falhou ficava indistinguível de um que indexou — e o agente só
descobre depois, ao consultar um índice vazio, sem nada em lugar nenhum dizendo
por quê.
"""

import logging
from unittest.mock import MagicMock

from academic_hunter.core.pipeline.steps import IndexResultsStep


def make_step(index_result):
    hunter = MagicMock()
    hunter.consolidated_results = {"a": {"Title": "A paper"}}
    store = MagicMock()
    store.index_papers.return_value = index_result
    hunter.pipeline.vector_store = store
    return IndexResultsStep(hunter), store


def test_a_successful_indexing_is_reported(caplog):
    step, _ = make_step(True)

    with caplog.at_level(logging.INFO):
        step.run()

    assert caplog.records, "a successful indexing said nothing"


def test_a_failed_indexing_is_not_silent(caplog):
    """The failure branch was empty: the return value was read and discarded."""
    step, _ = make_step(False)

    with caplog.at_level(logging.INFO):
        step.run()

    raised = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert raised, (
        "a failed indexing produced no warning — the run looks exactly like one "
        "that indexed, and the agent finds an empty index with no explanation"
    )


def test_a_missing_vector_store_is_still_explained(caplog):
    """The other quiet path, for contrast: it does say something."""
    hunter = MagicMock()
    hunter.consolidated_results = {"a": {"Title": "A paper"}}
    hunter.pipeline.vector_store = None

    with caplog.at_level(logging.INFO):
        IndexResultsStep(hunter).run()

    assert caplog.records, "a missing vector store was skipped silently"
