"""A query que cada fonte recebe, e por que as formas diferem.

Separado dos testes de parsing de cada conector porque a forma é justamente o
que quebrou. Medido contra as APIs reais, com as mesmas quatro âncoras Stellar:

    Semantic Scholar   frases soltas          51 resultados
                       com aspas e OR          0
    DOAJ               com aspas e OR         21
                       frases soltas            0
    CORE               com title:/abstract:  500 (erro do backend)
                       sem os prefixos         21

Os três querem sintaxes diferentes e concordam sobre os termos — é por isso que
a seleção e a junção são funções separadas.
"""

import logging
from unittest.mock import MagicMock

from academic_hunter.plugins.connectors.base import keyword_terms, quoted_ors
from academic_hunter.plugins.connectors.core_ac import CoreConnector
from academic_hunter.plugins.connectors.doaj import DoajConnector
from academic_hunter.plugins.connectors.semanticscholar import SemanticScholarConnector

ANCHORS = ["stellar blockchain", "soroban"]
FALLBACK = ["smart contract", "stablecoin"]


def _connector(cls):
    conn = cls(
        cache=MagicMock(),
        settings={},
        query_history=[],
        lock=MagicMock(),
        semaphore=MagicMock(),
        use_cache=False,
    )
    conn._make_request = MagicMock(return_value={"results": [], "total": 0})
    return conn


def _query(conn, anchors=ANCHORS, tech=FALLBACK):
    conn.fetch(anchors, tech, limit=5)
    return conn.query_history[-1]["Query"]


# ── a seleção dos termos ─────────────────────────────────────────────


def test_the_terms_are_the_anchors():
    """Um termo de fallback não entra: medido, ele estreita em vez de ampliar."""
    assert keyword_terms(ANCHORS, FALLBACK) == ANCHORS


def test_the_terms_fall_back_when_there_are_no_anchors():
    """Sem âncora nenhuma, `keyword_only_terms` é o que sobra — e é o seu papel."""
    assert keyword_terms([], FALLBACK) == FALLBACK


def test_terms_are_deduplicated():
    assert keyword_terms([], ["b", "B", "c"]) == ["b", "c"]


def test_the_cap_names_what_it_dropped(caplog):
    """As fatias antigas cortavam em silêncio; o corte passa a ser audível."""
    with caplog.at_level(logging.WARNING):
        kept = keyword_terms([f"t{i}" for i in range(8)], [], max_terms=3)

    assert kept == ["t0", "t1", "t2"]
    assert "t3" in caplog.text and "t7" in caplog.text


def test_quoted_ors():
    assert quoted_ors(["a b", "c"]) == '"a b" OR "c"'


# ── a sintaxe de cada fonte ──────────────────────────────────────────


def test_semantic_scholar_joins_plain_phrases():
    """Com aspas e OR este endpoint devolve nada: medido 0 contra 51."""
    assert _query(_connector(SemanticScholarConnector)) == "stellar blockchain soroban"


def test_doaj_joins_quoted_ors():
    """Com frases soltas o DOAJ lê conjunção e devolve nada: medido 0 contra 21."""
    assert _query(_connector(DoajConnector)) == '"stellar blockchain" OR "soroban"'


def test_core_carries_no_field_prefixes():
    """`title:`/`abstract:` fazem o CORE responder 500 — que se lê como "sem resultados".

    O `_make_request` trata qualquer não-200 como None, e o `fetch` devolve lista
    vazia. Foi assim que o CORE publicou `CORE: 0` em todo run sem nunca ter sido
    consultado de fato.
    """
    query = _query(_connector(CoreConnector))

    assert query == (
        '("stellar blockchain" OR "soroban") AND ("smart contract" OR "stablecoin")'
    )
    assert "title:" not in query
    assert "abstract:" not in query
