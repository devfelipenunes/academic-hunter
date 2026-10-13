"""Um marcador no lugar do resumo é ausência de resumo, e é contado como tal.

O gate de âncoras e o term tally correm sobre título e resumo concatenados. Com
o resumo vazio correm sobre o título sozinho, e o que sai dali não é comparável
com o que saiu de um paper lido: foi assim que dois registos de 14,2 e 14,7 —
os dois maiores tallies do run 20261008_091529 — ficaram com um
``Relevance_Score`` de 1,0 e 0,8. Nenhum artefacto dizia que lhes faltava o
resumo.

Dois cuidados que estes testes fixam: o marcador é reconhecido pelo valor
inteiro e nunca por substring (um resumo a sério que diga "abstract" fica
intacto), e a ausência é divulgada em vez de escondida — nenhum paper é
removido por causa disto.
"""

import pytest

from academic_hunter.core.models.schema import FIELD_SCHEMA
from academic_hunter.core.models.strategies import strategy_longest_string
from academic_hunter.core.models.utils import (
    ABSTRACT_PLACEHOLDERS,
    abstract_summary,
    has_abstract,
    strip_abstract_placeholder,
)


@pytest.mark.parametrize("marker", sorted(ABSTRACT_PLACEHOLDERS))
def test_every_marker_normalises_to_an_empty_abstract(marker):
    assert strip_abstract_placeholder(marker) == ""
    assert strip_abstract_placeholder(marker.upper()) == ""


def test_a_marker_marked_up_as_text_is_still_a_marker():
    """Vem da API com pontuação e espaços à volta, ou não vem."""
    for value in (" Abstract. ", "SEM ABSTRACT:", "No abstract —", "\nSem  resumo\n"):
        assert strip_abstract_placeholder(value) == ""


def test_nothing_at_all_is_an_empty_abstract():
    for value in (None, "", "   ", "\n\t"):
        assert strip_abstract_placeholder(value) == ""


def test_a_real_abstract_that_says_abstract_is_left_alone():
    """A armadilha da substring, que destruiria resumos verdadeiros.

    O match é sobre o valor colapsado inteiro. Se fosse ``in``, qualquer resumo
    que mencionasse a palavra perdia o texto todo — e um resumo truncado é um
    julgamento sobre outro documento.
    """
    text = "This abstract summarises a study of land registries on a ledger."
    assert strip_abstract_placeholder(text) == text
    assert strip_abstract_placeholder("SEM ABSTRACT") == ""
    assert strip_abstract_placeholder("SEM ABSTRACTLY") == "SEM ABSTRACTLY"


def test_a_real_abstract_is_returned_collapsed_and_not_altered():
    """O valor passa pelo mesmo colapso de espaços que o título."""
    assert strip_abstract_placeholder("  Two\n  lines.  ") == "Two lines."


def test_has_abstract_reads_either_spelling_of_the_field():
    """O sidecar escreve as colunas em minúsculas; o schema escreve ``Abstract``."""
    assert has_abstract({"Abstract": "Body."})
    assert has_abstract({"abstract": "Body."})
    assert not has_abstract({"Abstract": ""})
    assert not has_abstract({"abstract": "   "})
    assert not has_abstract({"Abstract": "sem resumo"})


def test_the_longest_string_strategy_does_not_prefer_a_marker():
    """A janela em que o marcador ganha é estreita, e é por isso que é fácil perdê-la.

    A estratégia de fusão escolhe o valor **mais longo**, e o marcador tem doze
    caracteres: contra qualquer resumo verdadeiro mais longo do que isso perde
    sozinho. Só quando o outro valor não é maior — um registo cujo texto real é
    ``See the PDF.``, ou o vazio — é que o marcador fica com o campo, e o campo
    passa a dizer que há um resumo onde não há.

    É a razão de a normalização estar também no ``FIELD_SCHEMA`` e não só no
    funil por onde o paper entra. O contraste é afirmado de propósito: a
    primeira asserção é o que acontece sem a entrada no schema.
    """
    assert strategy_longest_string("SEM ABSTRACT", "See the PDF.") == "SEM ABSTRACT"
    assert strategy_longest_string("SEM ABSTRACT", "") == "SEM ABSTRACT"

    normalize = FIELD_SCHEMA["Abstract"]["normalize"]
    assert strategy_longest_string(
        normalize("SEM ABSTRACT"), normalize("See the PDF.")
    ) == "See the PDF."


def test_the_summary_counts_the_papers_and_names_them():
    papers = [
        {"Title": "Read in full", "Abstract": "Body."},
        {"Title": "Title only", "Abstract": ""},
        {"Title": "Marked", "Abstract": "No abstract"},
    ]

    summary = abstract_summary(papers)

    assert summary["papers"] == 3
    assert summary["with_abstract"] == 1
    assert summary["without_abstract"] == 2
    assert summary["without_abstract_titles"] == ["Title only", "Marked"]


def test_the_summary_of_an_empty_corpus_is_zero_and_not_an_error():
    summary = abstract_summary([])

    assert summary["papers"] == 0
    assert summary["without_abstract"] == 0
    assert summary["without_abstract_titles"] == []


def test_the_summary_reads_the_lower_case_sidecar_shape():
    """O mesmo resumo descreve a colecção e o artefacto escrito dela."""
    summary = abstract_summary([{"title": "Sidecar row", "abstract": "Body."}])

    assert summary["with_abstract"] == 1
