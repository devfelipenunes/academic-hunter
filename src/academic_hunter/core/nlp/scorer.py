import math
import re
from typing import List, Dict, Any

class AcademicScorer:
    """Calculates relevance scores, detects anchors and normalizes terms for academic search."""
    def __init__(self, anchors: Dict[str, List[str]], tech_strings: Dict[str, List[str]], tech_weights: Dict[str, float], settings: Dict[str, Any]):
        self.anchors = anchors
        self.tech_strings = tech_strings
        self.tech_weights = tech_weights
        self.settings = settings
        
        # Pre-compile patterns
        self.compiled_patterns = {
            term: (re.compile(rf'\b{re.escape(term.lower())}\b'), weight)
            for term, weight in self.tech_weights.items()
        }
        self.anchor_patterns = {
            term: re.compile(rf'\b{re.escape(term.lower())}\b')
            for cat_list in self.anchors.values() for term in cat_list
        }
        self.tech_term_patterns = {
            term: re.compile(rf'\b{re.escape(term.lower())}\b')
            for cat_list in self.tech_strings.values() for term in cat_list
        }
        
    def generate_slug(self, title: str) -> str:
        if title is None: return ""
        return re.sub(r'\W+', '', str(title).lower())

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
                
        # Factor Citations score using logarithmic smoothing (base 10)
        citation_score = 0.0
        if citations > 0:
            citation_score = math.log10(citations + 1)
            
        final_score = score + citation_score
        return round(final_score, precision)

    def normalize_anchor(self, term: str) -> str:
        return term.strip().lower().replace(' ', '_').replace('-', '_')

    def find_matching_terms(self, text: str, terms_list: List[str]) -> str:
        if not text: return ""
        text_lower = str(text).lower()
        matches = set()
        for term in terms_list:
            pattern = self.anchor_patterns.get(term) or self.tech_term_patterns.get(term)
            if not pattern:
                pattern = re.compile(rf'\b{re.escape(term.lower())}\b')
                
            if pattern.search(text_lower):
                matches.add(term)
        return ", ".join(sorted(matches))

    def validate_anchor_context(self, text: str, matched_terms_str: str) -> bool:
        """Validates contextual relevance of matched terms (e.g. avoiding AI/ML Drex collision)."""
        if not matched_terms_str:
            return False
        found_list = [t.strip().lower() for t in matched_terms_str.split(',') if t.strip()]
        
        context_rules = self.settings.get("context_rules", {})
        text_lower = str(text).lower()
        
        for term in found_list:
            required_keywords = context_rules.get(term)
            if required_keywords:
                if not any(cw in text_lower for cw in required_keywords):
                    return False
        return True
