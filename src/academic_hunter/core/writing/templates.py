"""Article structures, derived from the author's own manuscripts.

The project contains three distinct paper shapes, and they are not
interchangeable — a survey written in method-paper form reads wrong, and vice
versa. Each is encoded here as data (an ordered list of sections with purpose,
target length and data sources) rather than as strings scattered through the
codebase, so the outline generator and the reviewers can agree on what a
complete article looks like.

Sources of truth:
    papers/conference-2027/paper.md  -> "method"   (~6,000 words)
    papers/joss-2026/paper.md        -> "software" (JOSS format)
    papers/tool-mapping/paper.md     -> "survey"   (~2,300 words)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# What a section can be filled from. The outline generator resolves these
# against the available run data; anything left unresolved becomes an explicit
# TODO marker rather than an invented number.
DATA_RUN_STATS = "run_stats"            # identified / duplicates / excluded / included
DATA_SOURCE_BREAKDOWN = "source_breakdown"  # counts per source
DATA_EXCLUSIONS = "exclusions_by_source"
DATA_CORPUS = "corpus"                  # papers retrieved in this run
DATA_EXPERIMENTS = "experiments"        # papers/experiments/results/*.json
DATA_PROSE = "prose"                    # nothing to inject — agent writes it


@dataclass(frozen=True)
class Section:
    """One section of an article."""

    name: str
    purpose: str
    target_words: int = 0
    data: List[str] = field(default_factory=list)
    number: Optional[str] = None  # "1", "2.1", ... — None when unnumbered
    subsections: List["Section"] = field(default_factory=list)


@dataclass(frozen=True)
class ArticleTemplate:
    """A complete article structure."""

    key: str
    label: str
    description: str
    source_example: str
    sections: List[Section]

    @property
    def total_words(self) -> int:
        """Target length, counting subsections and their children."""

        def count(sections: List[Section]) -> int:
            return sum(s.target_words + count(s.subsections) for s in sections)

        return count(self.sections)

    def section_names(self) -> List[str]:
        """Flat list of section names, parents before children."""
        names: List[str] = []

        def walk(sections: List[Section]) -> None:
            for s in sections:
                names.append(s.name)
                walk(s.subsections)

        walk(self.sections)
        return names


_METHOD = ArticleTemplate(
    key="method",
    label="Method paper",
    description=(
        "A contribution paper: a technique with formalisation and experiments. "
        "The most complete shape and the default for new technical content."
    ),
    source_example="papers/conference-2027/paper.md",
    sections=[
        Section(
            name="Abstract",
            number=None,
            purpose=(
                "One paragraph, ~180 words. States the technique, the key formula, "
                "and the headline result with its number."
            ),
            target_words=180,
            data=[DATA_EXPERIMENTS],
        ),
        Section(
            name="Introduction",
            number="1",
            purpose=(
                "Context, the gap, then contributions as a bolded bullet list — each "
                "bullet carries its own evidence number."
            ),
            target_words=630,
            data=[DATA_PROSE],
        ),
        Section(
            name="Method",
            number="2",
            purpose="Formal definition. Equations in block form with a 'where…' clause.",
            target_words=780,
            data=[DATA_PROSE],
            subsections=[
                Section("Background", purpose="Minimal setup the reader needs.", number="2.1",
                        target_words=90, data=[DATA_PROSE]),
                Section("Core formulation", purpose="The contribution itself.", number="2.2",
                        target_words=190, data=[DATA_PROSE]),
                Section("Details", purpose="Scaling, scoring, edge cases.", number="2.3",
                        target_words=270, data=[DATA_PROSE]),
                Section("Algorithm", purpose="Pseudocode block, line-numbered.", number="2.4",
                        target_words=170, data=[DATA_PROSE]),
            ],
        ),
        Section(
            name="Experiments",
            number="3",
            purpose=(
                "One subsection per experiment, each with its own numbered table, an "
                "interpretation paragraph and its significance (p-value, CI, effect size)."
            ),
            target_words=2520,
            data=[DATA_EXPERIMENTS],
            subsections=[
                Section("Setup", purpose="Corpus, configuration, baselines.", number="3.1",
                        target_words=65, data=[DATA_RUN_STATS]),
                Section("Ablation Study", purpose="Compare scoring modes.", number="3.2",
                        target_words=250, data=[DATA_EXPERIMENTS]),
                Section("Baseline Comparison", purpose="Against the obvious alternative.", number="3.4",
                        target_words=380, data=[DATA_EXPERIMENTS]),
                Section("Sensitivity", purpose="How it behaves as parameters move.", number="3.5",
                        target_words=150, data=[DATA_EXPERIMENTS]),
                Section("Computational Cost", purpose="Runtime and memory.", number="3.9",
                        target_words=160, data=[DATA_EXPERIMENTS]),
            ],
        ),
        Section(
            name="Related Work",
            number="4",
            purpose=(
                "Paragraph per approach, opening with the name in bold plus its citation "
                "key, closing by contrasting with this work."
            ),
            target_words=530,
            data=[DATA_CORPUS],
        ),
        Section(
            name="Conclusion",
            number="5",
            purpose="Restate the contribution, then numbered Limitations and Future work.",
            target_words=310,
            data=[DATA_EXPERIMENTS],
        ),
    ],
)

_SOFTWARE = ArticleTemplate(
    key="software",
    label="Software paper (JOSS)",
    description=(
        "The Journal of Open Source Software format: describes a tool rather than "
        "a technique. Unnumbered sections, one comparative feature table."
    ),
    source_example="papers/joss-2026/paper.md",
    sections=[
        Section(
            name="Summary",
            number=None,
            purpose=(
                "One paragraph, ~150 words. What the tool does, as a comma-separated "
                "capability list, ending with concrete numbers."
            ),
            target_words=150,
            data=[DATA_PROSE],
        ),
        Section(
            name="Statement of Need",
            number=None,
            purpose=(
                "The pain, the limitations of existing tools with citations, then the "
                "gap this fills — plus a comparative feature table."
            ),
            target_words=785,
            data=[DATA_PROSE],
        ),
        Section(
            name="Architecture",
            number=None,
            purpose="Diagram plus a numbered walkthrough of the pipeline.",
            target_words=415,
            data=[DATA_PROSE],
        ),
        Section(
            name="Related Work",
            number=None,
            purpose="Paragraph per approach, bolded lead, contrasting close.",
            target_words=660,
            data=[DATA_CORPUS],
        ),
        Section(
            name="Key Features",
            number=None,
            purpose="Bold-led bullet list, one capability per bullet.",
            target_words=190,
            data=[DATA_PROSE],
        ),
        Section(
            name="Quick Start",
            number=None,
            purpose="Shell and JSON code blocks that actually run.",
            target_words=120,
            data=[DATA_PROSE],
        ),
        Section(
            name="Experiments",
            number=None,
            purpose="Bold-led sub-blocks, each with its numbers.",
            target_words=310,
            data=[DATA_EXPERIMENTS],
        ),
        Section(
            name="Availability",
            number=None,
            purpose="Repository, archive DOI, documentation links.",
            target_words=100,
            data=[DATA_PROSE],
        ),
        Section(
            name="Conclusion",
            number=None,
            purpose="Two paragraphs plus a bolded Limitations line.",
            target_words=270,
            data=[DATA_EXPERIMENTS],
        ),
    ],
)

_SURVEY = ArticleTemplate(
    key="survey",
    label="Survey / mapping",
    description=(
        "Maps a landscape: states its own method, classifies what it finds, then "
        "argues a position. Shorter, argumentative, little or no mathematics."
    ),
    source_example="papers/tool-mapping/paper.md",
    sections=[
        Section(
            name="Abstract",
            number=None,
            purpose="Problem, method, contribution, headline finding — one paragraph.",
            target_words=196,
            data=[DATA_PROSE],
        ),
        Section(
            name="Introduction",
            number="1",
            purpose="Why the map is needed, then numbered contributions pointing at their section.",
            target_words=290,
            data=[DATA_PROSE],
        ),
        Section(
            name="Method",
            number="2",
            purpose=(
                "How items were identified and selected, and — explicitly — what the "
                "method's limitations are."
            ),
            target_words=205,
            data=[DATA_PROSE],
            subsections=[
                Section("Identification", purpose="Channels used to find items.", number="2.1",
                        target_words=60, data=[DATA_PROSE]),
                Section("Inclusion criteria", purpose="What qualifies.", number="2.2",
                        target_words=50, data=[DATA_PROSE]),
                Section("Exclusion criteria", purpose="What does not.", number="2.3",
                        target_words=45, data=[DATA_PROSE]),
                Section("Limitations", purpose="Declare what this method cannot claim.", number="2.4",
                        target_words=50, data=[DATA_PROSE]),
            ],
        ),
        Section(
            name="Taxonomy",
            number="3",
            purpose="Categories as a table, plus the boundary cases that make it interesting.",
            target_words=360,
            data=[DATA_CORPUS],
        ),
        Section(
            name="Empirical result",
            number="4",
            purpose="The measurement, with setup, result tables and caveats.",
            target_words=400,
            data=[DATA_EXPERIMENTS, DATA_SOURCE_BREAKDOWN],
        ),
        Section(
            name="Comparative matrix",
            number="5",
            purpose="Criteria by tool, boolean matrix.",
            target_words=270,
            data=[DATA_PROSE],
        ),
        Section(
            name="Positioning",
            number="6",
            purpose="Per-axis verdict — where it leads and where it trails.",
            target_words=240,
            data=[DATA_PROSE],
        ),
        Section(
            name="The field's gap",
            number="7",
            purpose="What the survey reveals is missing across the landscape.",
            target_words=230,
            data=[DATA_PROSE],
        ),
        Section(
            name="Conclusion",
            number="8",
            purpose="Restate findings and the recommendation.",
            target_words=140,
            data=[DATA_PROSE],
        ),
    ],
)

TEMPLATES: Dict[str, ArticleTemplate] = {
    _METHOD.key: _METHOD,
    _SOFTWARE.key: _SOFTWARE,
    _SURVEY.key: _SURVEY,
}


def get_template(key: str) -> ArticleTemplate:
    """Look up a template by key.

    Raises:
        KeyError: if the key is unknown — with the valid keys in the message, so
            a caller (or an agent) can self-correct without reading the source.
    """
    try:
        return TEMPLATES[key]
    except KeyError:
        raise KeyError(
            f"Unknown paper type {key!r}. Available: {', '.join(sorted(TEMPLATES))}"
        ) from None


def list_templates() -> List[ArticleTemplate]:
    """All templates, in a stable order."""
    return [TEMPLATES[k] for k in ("method", "software", "survey")]
