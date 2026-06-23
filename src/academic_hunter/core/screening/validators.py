from typing import Dict, Any, List
from ..nlp import AcademicScorer
from ..infra import HunterConfig

class PaperValidator:
    def __init__(self, config: HunterConfig, scorer: AcademicScorer):
        self.config = config
        self.scorer = scorer

    def validate_and_score(self, paper: Dict[str, Any], title: str, tech_list: List[str]) -> tuple[bool, str, str, str, float, str]:
        """Runs temporal and anchor filters, calculates relevance score, and matches tech terms."""
        # 1. Temporal Filter
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

        # 2. Industry Anchor Matching Check
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

        # 3. Score Calculation & Tech Terms Matching
        relevance_score = self.scorer.calculate_score(title, paper.get('Abstract', ''), paper.get('Citations', 0))
        matched_tech_terms = self.scorer.find_matching_terms(text_to_check, tech_list)

        return True, "", matched_anchor_cat, matched_anchor_terms, relevance_score, matched_tech_terms
