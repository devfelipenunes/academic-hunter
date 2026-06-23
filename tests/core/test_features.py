import unittest
import math
import re
import json
from typing import Dict, List, Any

# Mock version of the classes we are building to validate the logic
class NewFeatureScoringMixin:
    def __init__(self, tech_weights: Dict[str, float], title_multiplier: float = 1.5, score_precision: int = 1):
        self.tech_weights = tech_weights
        self.title_multiplier = title_multiplier
        self.score_precision = score_precision
        
        # Compile patterns with suffix "s?" for basic pluralization matching
        self.compiled_patterns = {
            term: (re.compile(rf'\b{re.escape(term.lower())}s?\b'), weight)
            for term, weight in self.tech_weights.items()
        }

    def calculate_score(self, title: str, abstract: str, citations: int = 0) -> float:
        score = 0.0
        title_lower = str(title).lower() if title else ""
        abstract_lower = str(abstract).lower() if abstract else ""
        
        for term, (pattern, weight) in self.compiled_patterns.items():
            # Check Title (bonus multiplier)
            if pattern.search(title_lower):
                score += (weight * self.title_multiplier)
            else:
                # Check Abstract with logarithmic TF scaling
                matches = pattern.findall(abstract_lower)
                if matches:
                    tf_factor = 1 + math.log(len(matches))
                    score += (weight * tf_factor)
                    
        # Citation bonus: 0.1 * ln(1 + Citations)
        if citations > 0:
            score += 0.1 * math.log(1 + citations)
            
        return round(score, self.score_precision)

class NewFeatureDeduplicatorAndPrisma:
    def __init__(self, min_relevance_score: float = 5.0):
        self.min_relevance_score = min_relevance_score
        self.consolidated_results = {}
        self.seen_ids = set()
        self.seen_dois = set()
        self.doi_to_slug = {}
        
        # Stats splits
        self.stats = {
            "identified": {},
            "duplicates_removed": 0,
            "excluded_year": 0,
            "excluded_anchors": 0,
            "excluded_technical_score": 0,
            "included_final": 0
        }
        
        # Predefined mock weight and patterns
        self.scorer = NewFeatureScoringMixin({"blockchain": 5.0, "interoperability": 3.0})
        self.anchors = ["pix", "cbdc"]

    def generate_slug(self, title: str) -> str:
        if title is None: return ""
        return re.sub(r'\W+', '', str(title).lower())

    def normalize_anchor(self, term: str) -> str:
        t = term.lower()
        for qualifier in [" payment", " banking", " card", " api", " services", " financial"]:
            t = t.replace(qualifier, "")
        return t.strip()

    def find_matching_terms(self, text: str, terms_list: List[str]) -> str:
        if not text: return ""
        text_lower = text.lower()
        matches = set()
        has_finance_context = None
        
        for term in terms_list:
            norm = self.normalize_anchor(term)
            pattern = re.compile(rf'\b{re.escape(norm)}s?\b')
            if pattern.search(text_lower):
                if norm in ["stone", "rede", "chips", "visa", "discover", "cielo"]:
                    if has_finance_context is None:
                        has_finance_context = any(
                            re.search(rf'\b{re.escape(ctx)}s?\b', text_lower)
                            for ctx in [
                                "payment", "settlement", "banking", "rtgs", "ledger", "liquidity", 
                                "clearing", "transaction", "fintech", "finance", "transfer", "currency"
                            ]
                        )
                    if has_finance_context:
                        matches.add(term)
                else:
                    matches.add(term)
        return ", ".join(sorted(matches))

    def _merge_paper_metadata(self, existing: Dict, new: Dict, anchor_cat: str, tech_cat: str):
        if new.get('Citations', 0) > existing.get('Citations', 0):
            existing['Citations'] = new['Citations']
        if len(new.get('Abstract', '')) > len(existing.get('Abstract', '')):
            existing['Abstract'] = new['Abstract']
        if not existing.get('URL') and new.get('URL'):
            existing['URL'] = new['URL']
        
        # Merge Sources
        sources = set(existing.get('Source', '').split(', '))
        sources.add(new.get('Source', ''))
        existing['Source'] = ', '.join(sorted(filter(None, sources)))

    def process_paper(self, paper: Dict, anchor_cat: str, tech_cat: str):
        source = paper.get("Source", "Unknown")
        self.stats["identified"][source] = self.stats["identified"].get(source, 0) + 1
        
        title = paper.get("Title", "").strip()
        if not title: return
        
        dedup_id = self.generate_slug(title)
        
        # DOI Normalization
        raw_doi = paper.get("DOI")
        doi_clean = ""
        if raw_doi:
            doi_clean = str(raw_doi).strip().lower().replace('https://doi.org/', '').replace('http://doi.org/', '').replace('dx.doi.org/', '')

        is_duplicate = False
        matched_existing_slug = None
        
        # Deduplication check
        if dedup_id in self.seen_ids:
            is_duplicate = True
            matched_existing_slug = dedup_id
        elif doi_clean and doi_clean in self.seen_dois:
            is_duplicate = True
            matched_existing_slug = self.doi_to_slug.get(doi_clean)
            
        if is_duplicate:
            self.stats["duplicates_removed"] += 1
            if matched_existing_slug and matched_existing_slug in self.consolidated_results:
                self._merge_paper_metadata(self.consolidated_results[matched_existing_slug], paper, anchor_cat, tech_cat)
            return

        # Register as seen
        self.seen_ids.add(dedup_id)
        if doi_clean:
            self.seen_dois.add(doi_clean)
            self.doi_to_slug[doi_clean] = dedup_id

        # Anchor filtering check
        full_text = f"{title} {paper.get('Abstract', '')}".lower()
        matched_anchors = self.find_matching_terms(full_text, self.anchors)
        if not matched_anchors:
            self.stats["excluded_anchors"] += 1
            return

        # Scoring
        score = self.scorer.calculate_score(title, paper.get("Abstract", ""), paper.get("Citations", 0))
        paper.update({
            "Relevance_Score": score,
            "Matched_Anchors": matched_anchors,
            "Anchor_Category": anchor_cat,
            "Tech_Category": tech_cat
        })
        
        if score >= self.min_relevance_score:
            self.consolidated_results[dedup_id] = paper
            self.stats["included_final"] += 1
        else:
            self.stats["excluded_technical_score"] += 1


class TestNewFeaturesValidation(unittest.TestCase):
    def test_scoring_enhancements(self):
        # 1. Test basic plural matching "s?"
        scorer = NewFeatureScoringMixin({"blockchain": 5.0})
        # "blockchains" (plural) should match and score
        score_plural = scorer.calculate_score("About Blockchains", "")
        self.assertEqual(score_plural, 7.5) # 5.0 * 1.5 multiplier for title match
        
        # 2. Test TF (Term Frequency) log scaling in abstract
        # 1 match in abstract: 5.0 * (1 + ln(1)) = 5.0
        score_1_tf = scorer.calculate_score("", "blockchain")
        self.assertEqual(score_1_tf, 5.0)
        
        # 3 matches in abstract: 5.0 * (1 + ln(3)) = 5.0 * (1 + 1.0986) = 10.5
        score_3_tf = scorer.calculate_score("", "blockchain blockchain blockchain")
        self.assertEqual(score_3_tf, 10.5)
        
        # 3. Test citation bonus
        # Citations = 100: adds 0.1 * ln(101) = 0.1 * 4.615 = 0.5 points
        score_citation = scorer.calculate_score("Blockchain Title", "", citations=100)
        self.assertEqual(score_citation, 8.0) # 7.5 (title) + 0.5 (citation) = 8.0

    def test_doi_deduplication(self):
        engine = NewFeatureDeduplicatorAndPrisma()
        
        paper1 = {
            "Title": "First Title",
            "Abstract": "Blockchain technology for Pix.",
            "Citations": 10,
            "DOI": "10.1000/xyz123",
            "Source": "ArXiv"
        }
        paper2 = {
            "Title": "Different Title But Same DOI",
            "Abstract": "Blockchain technology for Pix.",
            "Citations": 20,
            "DOI": "https://doi.org/10.1000/xyz123", # Clean URL to DOI
            "Source": "Crossref"
        }
        
        engine.process_paper(paper1, "cat1", "cat2")
        engine.process_paper(paper2, "cat1", "cat2")
        
        # Should deduplicate based on the DOI
        self.assertEqual(len(engine.consolidated_results), 1)
        self.assertEqual(engine.stats["duplicates_removed"], 1)
        # Citations merged/updated to 20
        self.assertEqual(engine.consolidated_results["firsttitle"]["Citations"], 20)
        # Sources merged
        self.assertEqual(engine.consolidated_results["firsttitle"]["Source"], "ArXiv, Crossref")

    def test_prisma_professional_split(self):
        engine = NewFeatureDeduplicatorAndPrisma(min_relevance_score=5.0)
        
        # Paper 1: Passes anchors, passes score
        p1 = {"Title": "A", "Abstract": "Pix blockchain", "Source": "S1"}
        # Paper 2: Fails anchors
        p2 = {"Title": "B", "Abstract": "Some general stuff", "Source": "S1"}
        # Paper 3: Passes anchors, fails score (no blockchain term)
        p3 = {"Title": "C", "Abstract": "Pix payment only", "Source": "S1"}
        
        engine.process_paper(p1, "cat", "cat")
        engine.process_paper(p2, "cat", "cat")
        engine.process_paper(p3, "cat", "cat")
        
        self.assertEqual(engine.stats["included_final"], 1)
        self.assertEqual(engine.stats["excluded_anchors"], 1) # p2
        self.assertEqual(engine.stats["excluded_technical_score"], 1) # p3
        self.assertEqual(engine.stats["identified"]["S1"], 3)

    def test_dblp_parser_mock(self):
        # Sample response JSON format of DBLP API
        dblp_response = {
            "result": {
                "hits": {
                    "hit": [
                        {
                            "info": {
                                "title": "Blockchain in Pix Payments",
                                "year": "2024",
                                "venue": "ACM",
                                "doi": "10.1145/12345",
                                "url": "https://dblp.org/rec/123",
                                "type": "Conference"
                            }
                        }
                    ]
                }
            }
        }
        
        # Parser logic
        hits = dblp_response.get("result", {}).get("hits", {}).get("hit", [])
        articles = []
        for hit in hits:
            info = hit.get("info", {})
            articles.append({
                "Title": info.get("title", ""),
                "Abstract": "",
                "Year": info.get("year", ""),
                "URL": info.get("url", ""),
                "Source": "DBLP",
                "Citations": 0,
                "DOI": info.get("doi"),
                "Type": info.get("type", ""),
                "Venue": info.get("venue", "")
            })
            
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["Title"], "Blockchain in Pix Payments")
        self.assertEqual(articles[0]["DOI"], "10.1145/12345")

    def test_doaj_parser_mock(self):
        # Sample response JSON format of DOAJ API
        doaj_response = {
            "results": [
                {
                    "bibjson": {
                        "title": "Decentralized Payments",
                        "abstract": "Analysis of CBDC and blockchain.",
                        "year": "2023",
                        "journal": {"title": "Springer Open"},
                        "identifier": [{"type": "doi", "id": "10.1007/54321"}],
                        "link": [{"url": "https://doaj.org/article/1"}]
                    }
                }
            ]
        }
        
        # Parser logic
        articles = []
        for res in doaj_response.get("results", []):
            bibjson = res.get("bibjson", {})
            doi = None
            for ident in bibjson.get("identifier", []):
                if ident.get("type") == "doi":
                    doi = ident.get("id")
                    break
            url = ""
            for link in bibjson.get("link", []):
                if link.get("url"):
                    url = link.get("url")
                    break
                    
            articles.append({
                "Title": bibjson.get("title", ""),
                "Abstract": bibjson.get("abstract", ""),
                "Year": bibjson.get("year", ""),
                "URL": url,
                "Source": "DOAJ",
                "Citations": 0,
                "DOI": doi,
                "Type": "journal-article",
                "Venue": bibjson.get("journal", {}).get("title", "")
            })
            
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["Title"], "Decentralized Payments")
        self.assertEqual(articles[0]["DOI"], "10.1007/54321")
        self.assertEqual(articles[0]["Abstract"], "Analysis of CBDC and blockchain.")

    def test_context_aware_filtering_and_sources_merge(self):
        engine = NewFeatureDeduplicatorAndPrisma()
        engine.anchors = ["Pix payment", "Stone payment", "FedNow"]
        
        # Test Unambiguous direct match: "Pix" matches even without "payment"
        p1 = {"Title": "A study of Pix", "Abstract": "blockchain technology", "Source": "S1"}
        engine.process_paper(p1, "cat", "cat")
        self.assertIn("Pix payment", engine.consolidated_results["astudyofpix"]["Matched_Anchors"])
        
        # Test Ambiguous match with context: "Stone" matches if financial context is present
        p2 = {"Title": "A study of Stone", "Abstract": "in instant retail payment processing with blockchain", "Source": "S2"}
        engine.process_paper(p2, "cat", "cat")
        self.assertIn("Stone payment", engine.consolidated_results["astudyofstone"]["Matched_Anchors"])
        
        # Test Ambiguous mismatch without context: "Stone" alone in title with geology abstract gets excluded
        p3 = {"Title": "A study of Stone Geology", "Abstract": "in ancient geology", "Source": "S3"}
        engine.process_paper(p3, "cat", "cat")
        self.assertEqual(engine.stats["excluded_anchors"], 1)


if __name__ == "__main__":
    unittest.main()
