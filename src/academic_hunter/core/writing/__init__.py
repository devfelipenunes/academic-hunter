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

from .templates import ArticleTemplate, get_template, list_templates
from .style import (
    format_bibtex_key,
    format_citation,
    format_equation,
    format_statistical_claim,
    format_table,
)
from .outline import RunData, build_outline
from .citations import (
    CitationCandidate,
    ExistenceProbes,
    ExistenceResult,
    extract_citations,
    parse_bibtex_entries,
    parse_bibtex_keys,
    summarize as summarize_citations,
    verify_existence,
)
from .numbers import (
    NumericClaim,
    NumberResult,
    extract_claims,
    index_results,
    summarize_numbers,
    verify_numbers,
)

__all__ = [
    # templates
    "ArticleTemplate",
    "get_template",
    "list_templates",
    # style
    "format_citation",
    "format_table",
    "format_equation",
    "format_bibtex_key",
    "format_statistical_claim",
    # outline
    "RunData",
    "build_outline",
    # citations
    "CitationCandidate",
    "ExistenceProbes",
    "ExistenceResult",
    "extract_citations",
    "parse_bibtex_entries",
    "parse_bibtex_keys",
    "summarize_citations",
    "verify_existence",
    # numbers
    "NumericClaim",
    "NumberResult",
    "extract_claims",
    "index_results",
    "summarize_numbers",
    "verify_numbers",
]
