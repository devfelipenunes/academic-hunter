"""Falha de rede não pode virar "esta referência não existe".

`doi_resolves` é uma sonda **refutadora**: uma resposta negativa prova que a
referência não existe. O contrato em `core/writing/citations.py` diz que os
callables devolvem `None` quando não conseguem decidir, e que "a None never
counts as a failure". Devolver `False` para timeout, 429 e 5xx transforma
indisponibilidade momentânea em prova de inexistência — e o veredito que sai
disso é NOT_FOUND, que é uma acusação.
"""

from unittest.mock import MagicMock, patch

import pytest

BIB = """@article{study2024,
  title = {A Study of Ledgers},
  doi = {10.1/example},
  year = {2024}
}
"""

TEXT = "The approach follows earlier work [@study2024] on ledgers."


def _response(status_code):
    response = MagicMock()
    response.status_code = status_code
    return response


async def _verify(tmp_path, mock_ctx, *, status=None, raises=None):
    from academic_hunter.interfaces.mcp.tools.writing import verify_citations

    bib = tmp_path / "refs.bib"
    bib.write_text(BIB, encoding="utf-8")

    def fake_get(*args, **kwargs):
        if raises is not None:
            raise raises
        return _response(status)

    with patch("requests.get", side_effect=fake_get), \
         patch("academic_hunter.interfaces.mcp.tools.writing._get_vector_store", return_value=None):
        return await verify_citations(mock_ctx, TEXT, bib_path=str(bib))


NOT_FOUND_SECTION = "## Not found"
UNVERIFIABLE_SECTION = "## Unverifiable"


async def test_a_doi_that_resolves_is_verified(tmp_path, mock_ctx):
    report = await _verify(tmp_path, mock_ctx, status=200)
    assert "## Verified" in report
    assert NOT_FOUND_SECTION not in report


async def test_a_404_is_evidence_the_reference_does_not_exist(tmp_path, mock_ctx):
    report = await _verify(tmp_path, mock_ctx, status=404)
    assert NOT_FOUND_SECTION in report


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_a_server_that_cannot_answer_does_not_override_the_bibliography(
    tmp_path, mock_ctx, status
):
    """The `.bib` already confirmed this key; Crossref having a bad minute is not
    evidence against it, and it certainly does not outrank the file the author
    is citing from."""
    report = await _verify(tmp_path, mock_ctx, status=status)
    assert NOT_FOUND_SECTION not in report, f"HTTP {status} was read as 'the reference is fake'"
    assert "## Verified" in report


async def test_a_timeout_does_not_override_the_bibliography(tmp_path, mock_ctx):
    import requests

    report = await _verify(tmp_path, mock_ctx, raises=requests.Timeout("timed out"))
    assert NOT_FOUND_SECTION not in report, "a timeout was read as 'the reference is fake'"
    assert "## Verified" in report
