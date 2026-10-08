import math
import re
from typing import Any, Dict, Iterable, List, Tuple


def title_slug(title: Any) -> str:
    """Slug form of a title — the identity of a paper that carries no DOI."""
    if title is None:
        return ""
    return re.sub(r"\W+", "", str(title).lower())


def _term_pattern(term: str) -> "re.Pattern[str]":
    """How one term is matched inside a title or an abstract.

    A boundary is asserted only where the term's own edge is a word character.
    ``\\b`` asserts both sides at once, and demanding a word character where the
    term has none is unsatisfiable: after the final ``+`` of ``c++`` comes a
    space, and ``+`` to a space is not a boundary — so the term could not match,
    however plainly the abstract spelled it out. ``c#`` failed the same way, and
    a leading ``.net`` failed whenever it began the string, because a non-word
    character at position zero is not a boundary either.

    Where an edge is already a non-word character it separates the term by
    itself, and no guard is added — ``c++`` written inside ``c++builder`` is a
    judgement the term list makes, not this function.
    """
    lowered = term.lower()
    pattern = re.escape(lowered)
    if lowered[:1].isalnum() or lowered.startswith("_"):
        pattern = r"(?<!\w)" + pattern
    if lowered[-1:].isalnum() or lowered.endswith("_"):
        pattern = pattern + r"(?!\w)"
    return re.compile(pattern)


def terms_of(groups: Dict[str, List[str]]) -> List[str]:
    """The terms of a ``{category: [term]}`` mapping, flattened in order."""
    return [term for group in groups.values() for term in group]


def compile_term_patterns(terms: Iterable[str]) -> Dict[str, "re.Pattern[str]"]:
    """One pattern per term, for the flat term lists of anchors and tech strings."""
    return {term: _term_pattern(term) for term in terms}


def compile_weighted_patterns(
    weights: Dict[str, float],
) -> Dict[str, Tuple["re.Pattern[str]", float]]:
    """One ``(pattern, weight)`` per term — the terms a score is built from."""
    return {term: (_term_pattern(term), weight) for term, weight in weights.items()}


class AcademicScorer:
    """Calculates relevance scores, detects anchors and normalizes terms for academic search."""
    def __init__(self, anchors: Dict[str, List[str]], tech_strings: Dict[str, List[str]], tech_weights: Dict[str, float], context_rules: Dict[str, List[str]], settings: Dict[str, Any]):
        self.anchors = anchors
        self.tech_strings = tech_strings
        self.tech_weights = tech_weights
        self.context_rules = context_rules
        self.settings = settings
        self.recompile()

    def recompile(self) -> None:
        """Rebuild the three pattern maps from the current terms and weights.

        They are derived state. ``load()`` updates the mappings in place, so they
        read as current while the compiled patterns still hold the previous terms
        and weights — and nothing else rebuilds them.
        """
        self.compiled_patterns = compile_weighted_patterns(self.tech_weights)
        self.anchor_patterns = compile_term_patterns(terms_of(self.anchors))
        self.tech_term_patterns = compile_term_patterns(terms_of(self.tech_strings))

    def generate_slug(self, title: str) -> str:
        return title_slug(title)

    def calculate_score(self, title: str, abstract: str, citations: int = 0) -> float:
        score = 0.0
        title_lower = str(title).lower() if title else ""
        abstract_lower = str(abstract).lower() if abstract else ""
        
        multiplier = self.settings.get('title_multiplier', 1.5)
        precision = self.settings.get('score_precision', 1)
        
        for term, (pattern, weight) in self.compiled_patterns.items():
            if pattern.search(title_lower):
                score += (weight * multiplier)
            elif pattern.search(abstract_lower):
                score += weight
                
        citation_score = 0.0
        if citations > 0:
            citation_score = math.log10(citations + 1)
            
        final_score = score + citation_score
        return round(final_score, precision)

    def normalize_anchor(self, term: str) -> str:
        return term.strip().lower().replace(' ', '_').replace('-', '_')

    def compute_hybrid_score(
        self,
        title: str,
        abstract: str,
        citations: int,
        semantic_score: float,
        has_semantic: bool = False,
        ablation_mode: str = "hybrid",
        score_precision: int = 1,
    ) -> float:
        """Compute the inclusion score for a paper, respecting the ablation mode.

        Two distinct scores exist in this pipeline, with different roles:

        - **Inclusion score** (this function). Decides whether a paper passes
          the relevance threshold when it is first processed. This is where the
          ablation mode (keyword / embedding / hybrid) takes effect.
        - **Reported score** (``RecomputeRanksStep`` in ``core/pipeline/steps.py``).
          Rank-normalised to [0, 10] and written to ``Relevance_Score`` once the
          run completes, across the whole collection. This is what appears in
          exports, PRISMA reports and the final threshold filter.

        Changing this function changes *which papers are included*, not how they
        are ranked. Do not duplicate this math elsewhere — callers should route
        through here and the pipeline will re-rank afterwards.

        Args:
            title: Paper title.
            abstract: Paper abstract.
            citations: Citation count.
            semantic_score: Semantic relevance (0-1) from Weight-Bleeding.
            has_semantic: Whether semantic scoring is available.
            ablation_mode: One of 'hybrid', 'embedding', 'keyword'.
            score_precision: Decimal places for rounding.

        Returns:
            Final relevance score.
        """
        kw_score = self.calculate_score(title, abstract, citations)

        if has_semantic and ablation_mode != "keyword":
            sem = semantic_score if semantic_score > 0.0 else 0.0
            if ablation_mode == "embedding":
                return round(
                    math.sqrt(sem) * 10.0,
                    score_precision,
                )
            return round(
                (math.sqrt(sem) * 10.0) + (kw_score * 0.3),
                score_precision,
            )
        return round(kw_score, score_precision)

    def find_matching_terms(self, text: str, terms_list: List[str]) -> str:
        if not text: return ""
        text_lower = str(text).lower()
        matches = set()
        for term in terms_list:
            pattern = self.anchor_patterns.get(term) or self.tech_term_patterns.get(term)
            if not pattern:
                pattern = _term_pattern(term)
                
            if pattern.search(text_lower):
                matches.add(term)
        return ", ".join(sorted(matches))

    def validate_anchor_context(self, text: str, matched_terms_str: str) -> bool:
        """Validates contextual relevance of matched terms (e.g. avoiding AI/ML Drex collision)."""
        if not matched_terms_str:
            return False
        found_list = [t.strip().lower() for t in matched_terms_str.split(',') if t.strip()]
        
        text_lower = str(text).lower()
        
        for term in found_list:
            required_keywords = self.context_rules.get(term)
            if required_keywords:
                if not any(cw in text_lower for cw in required_keywords):
                    return False
        return True
