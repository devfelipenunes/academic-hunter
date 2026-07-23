import math
from typing import Dict, Any, List, Optional
from ..nlp import AcademicScorer
from ..infra import HunterConfig

class PaperValidator:
    def __init__(self, config: HunterConfig, scorer: AcademicScorer, semantic_screener=None):
        self.config = config
        self.scorer = scorer
        self.semantic_screener = semantic_screener

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

        matched_anchor_cat = ""
        matched_anchor_terms = ""
        text_to_check = f"{title} {paper.get('Abstract', '')}".lower()
        for cat, keywords in self.config.anchors.items():
            found_terms = self.scorer.find_matching_terms(text_to_check, keywords)
            if found_terms and self.scorer.validate_anchor_context(text_to_check, found_terms):
                matched_anchor_cat = cat
                matched_anchor_terms = found_terms
                break
                
        if not matched_anchor_cat:
            return False, "anchor", "", "", 0.0, ""

        relevance_score = self.scorer.calculate_score(title, paper.get('Abstract', ''), paper.get('Citations', 0))
        matched_tech_terms = self.scorer.find_matching_terms(text_to_check, tech_list)

        # Store raw score keys for rank normalization downstream
        paper["_kw_score"] = relevance_score

        # Hybrid scoring with ablation control
        ablation = self.config.settings.get('ablation', {})
        mode = ablation.get('mode', 'hybrid')

        if self.semantic_screener is not None and mode != 'keyword':
            sem_config = {
                "anchors": self.config.anchors,
                "technical_strings": self.config.tech_strings,
                "technical_weights": self.config.tech_weights,
            }
            semantic_score = self.semantic_screener.evaluate(paper, sem_config)
            paper["_sem_score"] = round(semantic_score, 4)

            if mode == 'embedding':
                # sqrt decompresses cosine similarity range: [0-1] → [0-1] but expanded at low end
                relevance_score = round(
                    math.sqrt(semantic_score) * 10.0,
                    int(self.config.settings.get('score_precision', 1)),
                )
            else:
                # Fused: sqrt(WB) as base, keyword as bonus (kw × 0.3)
                relevance_score = round(
                    (math.sqrt(semantic_score) * 10.0) + (relevance_score * 0.3),
                    int(self.config.settings.get('score_precision', 1)),
                )

        elif mode == 'keyword' and self.semantic_screener is not None:
            pass  # skip semantic, use regex score as-is

        return True, "", matched_anchor_cat, matched_anchor_terms, relevance_score, matched_tech_terms

    def compute_hybrid_score(self, paper: Dict[str, Any]) -> float:
        """Compute relevance score respecting ablation mode without re-checking year/anchor filters.

        Used by duplicate resolution to recalculate scores after metadata merge
        using the same ablation-aware logic as validate_and_score().
        """
        title = str(paper.get("Title", ""))
        abstract = str(paper.get("Abstract", ""))
        citations = int(paper.get("Citations", 0))

        relevance_score = self.scorer.calculate_score(title, abstract, citations)
        paper["_kw_score"] = relevance_score

        ablation = self.config.settings.get('ablation', {})
        mode = ablation.get('mode', 'hybrid')

        if self.semantic_screener is not None and mode != 'keyword':
            sem_config = {
                "anchors": self.config.anchors,
                "technical_strings": self.config.tech_strings,
                "technical_weights": self.config.tech_weights,
            }
            semantic_score = self.semantic_screener.evaluate(paper, sem_config)
            paper["_sem_score"] = round(semantic_score, 4)

            if mode == 'embedding':
                relevance_score = round(
                    math.sqrt(semantic_score) * 10.0,
                    int(self.config.settings.get('score_precision', 1)),
                )
            else:
                # Fused: sqrt(WB) as base, keyword as bonus (kw × 0.3)
                relevance_score = round(
                    (math.sqrt(semantic_score) * 10.0) + (relevance_score * 0.3),
                    int(self.config.settings.get('score_precision', 1)),
                )

        return relevance_score
