from typing import Any, Dict, List, Tuple

from ..infra import HunterConfig
from ..nlp import AcademicScorer
from ..nlp.scorer import term_matches
from .ablation import ablation_mode, semantic_scoring_enabled


class PaperValidator:
    def __init__(self, config: HunterConfig, scorer: AcademicScorer, semantic_screener=None):
        self.config = config
        self.scorer = scorer
        self.semantic_screener = semantic_screener

    @staticmethod
    def _text(paper: Dict[str, Any], title: str = None) -> str:
        return f"{title or paper.get('Title', '')} {paper.get('Abstract', '')}".lower()

    def match_anchor(self, paper: Dict[str, Any], title: str = None) -> Tuple[str, str]:
        """The first anchor group this text matches, and the terms that matched it.

        One rule with two callers. The validator asks before admitting a copy;
        the merge asks about an incoming duplicate, whose match was never
        computed because the duplicate path skips validation entirely. Without
        the second caller ``Anchor_Terms`` could only ever hold the first copy's
        terms while ``Anchor_Category`` accumulated every group the work was
        found under. Measured on the delivered run: 57 of 310 rows list two
        categories and the terms of one.
        """
        text = self._text(paper, title)
        title_text = str(title or paper.get("Title", "")).lower()
        excluded_title_terms = self.config.settings.get("context_exclude_title_terms", [])
        if isinstance(excluded_title_terms, str):
            excluded_title_terms = [excluded_title_terms]
        if isinstance(excluded_title_terms, (list, tuple)) and any(
            term_matches(title_text, str(term).strip())
            for term in excluded_title_terms
            if str(term).strip()
        ):
            return "", ""

        context_text = text
        if self.config.settings.get("context_rules_title_only") is True:
            context_text = title_text
        for cat, keywords in self.config.anchors.items():
            found_terms = self.scorer.find_matching_terms(text, keywords)
            if found_terms and self.scorer.validate_anchor_context(context_text, found_terms):
                return cat, found_terms
        return "", ""

    def anchor_rejection_detail(self, paper: Dict[str, Any], title: str = None) -> str:
        """Explain why a record failed the anchor gate without changing its outcome."""
        title_text = str(title or paper.get("Title", "")).lower()
        excluded_title_terms = self.config.settings.get("context_exclude_title_terms", [])
        if isinstance(excluded_title_terms, str):
            excluded_title_terms = [excluded_title_terms]
        if isinstance(excluded_title_terms, (list, tuple)) and any(
            term_matches(title_text, str(term).strip())
            for term in excluded_title_terms
            if str(term).strip()
        ):
            return "title_exclusion"

        text = self._text(paper, title)
        context_text = (
            title_text
            if self.config.settings.get("context_rules_title_only") is True
            else text
        )
        for keywords in self.config.anchors.values():
            found = self.scorer.find_matching_terms(text, keywords)
            if found and not self.scorer.validate_anchor_context(context_text, found):
                return "context_missing"
        return "anchor_missing"

    def match_tech_terms(self, paper: Dict[str, Any], tech_list: List[str], title: str = None) -> str:
        """The technical terms this text matches, by the same tally the validator uses."""
        return self.scorer.find_matching_terms(self._text(paper, title), tech_list)

    def validate_and_score(self, paper: Dict[str, Any], title: str, tech_list: List[str]) -> tuple[bool, str, str, str, float, str]:
        """Runs temporal and anchor filters, calculates relevance score, and matches tech terms."""
        year_val = paper.get("Year")
        start_year = self.config.settings.get('start_year', 2021)
        parsed_year = None
        if year_val not in [None, "N/A", "None", ""]:
            try:
                parsed_year = int(str(year_val)[:4])
            except ValueError:
                pass
                
        if parsed_year is not None and parsed_year < start_year:
            return False, "year", "", "", 0.0, ""

        matched_anchor_cat, matched_anchor_terms = self.match_anchor(paper, title)
        if not matched_anchor_cat:
            return False, "anchor", "", "", 0.0, ""

        relevance_score = self.scorer.calculate_score(title, paper.get('Abstract', ''), paper.get('Citations', 0))
        matched_tech_terms = self.match_tech_terms(paper, tech_list, title)

        paper["_kw_score"] = relevance_score

        mode = ablation_mode(self.config.settings)
        semantic_on = semantic_scoring_enabled(self.config.settings, self.semantic_screener)

        if semantic_on:
            sem_config = self.config.screener_config()
            semantic_score = self.semantic_screener.evaluate(paper, sem_config)
            paper["_sem_score"] = round(semantic_score, 4)
        else:
            semantic_score = 0.0

        relevance_score = self.scorer.compute_hybrid_score(
            title=title,
            abstract=paper.get('Abstract', ''),
            citations=paper.get('Citations', 0),
            semantic_score=semantic_score,
            has_semantic=semantic_on,
            ablation_mode=mode,
            score_precision=int(self.config.settings.get('score_precision', 1)),
        )

        return True, "", matched_anchor_cat, matched_anchor_terms, relevance_score, matched_tech_terms

    def compute_hybrid_score(self, paper: Dict[str, Any]) -> float:
        """Compute relevance score respecting ablation mode without re-checking year/anchor filters.

        Used by duplicate resolution to recalculate scores after metadata merge.
        Delegates to the centralized scorer method.
        """
        title = str(paper.get("Title", ""))
        abstract = str(paper.get("Abstract", ""))
        citations = int(paper.get("Citations", 0))

        ablation = self.config.settings.get('ablation', {})
        mode = ablation.get('mode', 'hybrid')

        kw_score = self.scorer.calculate_score(title, abstract, citations)
        paper["_kw_score"] = kw_score

        has_semantic = self.semantic_screener is not None and mode != 'keyword'
        semantic_score = 0.0
        if has_semantic:
            cached = paper.get("_sem_score")
            if cached is not None:
                semantic_score = float(cached)
            else:
                sem_config = self.config.screener_config()
                semantic_score = self.semantic_screener.evaluate(paper, sem_config)
                paper["_sem_score"] = round(semantic_score, 4)

        return self.scorer.compute_hybrid_score(
            title=title,
            abstract=abstract,
            citations=citations,
            semantic_score=semantic_score,
            has_semantic=has_semantic,
            ablation_mode=mode,
            score_precision=int(self.config.settings.get('score_precision', 1)),
        )
