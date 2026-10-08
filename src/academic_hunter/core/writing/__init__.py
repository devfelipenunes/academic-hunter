"""Scientific writing support: article templates, author style conventions and
deterministic outline generation.

This package is pure domain logic. It deliberately does **not** call an LLM and
does **not** import from ``academic_hunter.interfaces`` — the MCP layer wraps it.
The division of labour is:

- the tools here assemble structure, verified context and real numbers;
- the connected agent writes the prose.

That keeps the outline free of hallucination (it comes from a template plus the
run's own data) and preserves the project's offline, zero-cost, reproducible
character.
"""

from .citations import (
    CitationCandidate,
    ExistenceProbes,
    ExistenceResult,
    extract_citations,
    parse_bibtex_entries,
    parse_bibtex_keys,
    verify_existence,
)
from .citations import (
    summarize as summarize_citations,
)
from .numbers import (
    NumberResult,
    NumericClaim,
    extract_claims,
    index_results,
    summarize_numbers,
    verify_numbers,
)
from .outline import RunData, build_outline
from .style import (
    format_bibtex_key,
    format_citation,
    format_equation,
    format_statistical_claim,
    format_table,
    paper_citation_key,
)
from .templates import ArticleTemplate, get_template, list_templates

__all__ = [
    "ArticleTemplate",
    "get_template",
    "list_templates",
    "format_citation",
    "format_table",
    "format_equation",
    "format_bibtex_key",
    "paper_citation_key",
    "format_statistical_claim",
    "RunData",
    "build_outline",
    "CitationCandidate",
    "ExistenceProbes",
    "ExistenceResult",
    "extract_citations",
    "parse_bibtex_entries",
    "parse_bibtex_keys",
    "summarize_citations",
    "verify_existence",
    "NumericClaim",
    "NumberResult",
    "extract_claims",
    "index_results",
    "summarize_numbers",
    "verify_numbers",
]
