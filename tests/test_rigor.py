import unittest
import json
import tempfile
import shutil
import re
from pathlib import Path
from src.academic_hunter import AcademicHunter

class TestAcademicRigor(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory
        self.test_dir = tempfile.mkdtemp()
        self.config_path = Path(self.test_dir) / 'config.json'
        
        # Default test configuration
        config = {
            "settings": {"title_multiplier": 1.5, "score_precision": 1},
            "ancoras": {},
            "strings_tecnicas": {},
            "pesos_tecnicos": {}
        }
        
        # Write the config to the temporary file
        self.config_path.write_text(json.dumps(config))
        
        # Initialize AcademicHunter with the temporary config
        # Also redirect output_dir to temp to avoid cluttering workspace
        self.hunter = AcademicHunter(config_path=str(self.config_path), output_dir=self.test_dir)

    def tearDown(self):
        # Remove the temporary directory after the test
        shutil.rmtree(self.test_dir)

    def test_generate_slug(self):
        """Verify title normalization into a slug."""
        title1 = "Blockchain & ISO 20022: A Survey!"
        title2 = "blockchain iso 20022 a survey"
        expected = "blockchainiso20022asurvey"
        
        self.assertEqual(self.hunter.generate_slug(title1), expected)
        self.assertEqual(self.hunter.generate_slug(title2), expected)

    def test_generate_slug_non_string(self):
        """Verify generate_slug handles non-string inputs safely."""
        self.assertEqual(self.hunter.generate_slug(None), "")
        self.assertEqual(self.hunter.generate_slug(123), "123")

    def test_stats_initialization(self):
        """Verify PRISMA stats are initialized correctly."""
        expected_stats = {
            "identified": {},
            "duplicates_removed": 0,
            "excluded_score": 0,
            "included_final": 0
        }
        self.assertEqual(self.hunter.stats, expected_stats)

    def test_deduplication_and_stats(self):
        """Verify title-slug deduplication, citation updates, and PRISMA stats."""
        # Mock raw results from two different sources with same title but different citations
        mock_results = [
            {
                "Title": "Duplicate Paper",
                "Abstract": "First version.",
                "Year": "2021",
                "URL": "http://example.com/1",
                "Source": "SourceA",
                "Citations": 10,
                "DOI": "10.1234/1"
            },
            {
                "Title": "Duplicate Paper",
                "Abstract": "Second version.",
                "Year": "2021",
                "URL": "http://example.com/2",
                "Source": "SourceB",
                "Citations": 20,
                "DOI": "10.1234/2"
            },
            {
                "Title": "Low Score Paper",
                "Abstract": "Irrelevant content.",
                "Year": "2021",
                "URL": "http://example.com/3",
                "Source": "SourceA",
                "Citations": 5,
                "DOI": "10.1234/3"
            }
        ]
        
        # We need to manually trigger the logic that would be in run()
        # For this test, we'll mock the internal state and calls
        self.hunter.anchors = {"cat": ["duplicate", "low"]}
        self.hunter.settings["min_relevance_score"] = 5.0
        self.hunter.tech_weights = {"duplicate": 10.0, "low": 1.0}
        # self.hunter.load_config = lambda: None # Skip actual loading - already initialized in setUp
        self.hunter.compiled_patterns = {
            "duplicate": (re.compile(r'\bduplicate\b'), 10.0),
            "low": (re.compile(r'\blow\b'), 1.0)
        }
        self.hunter.anchor_patterns = {
            "duplicate": re.compile(r'\bduplicate\b'),
            "low": re.compile(r'\blow\b')
        }

        # Instead of calling run(), we'll implement a miniature version of the deduplication loop
        # to verify the logic we intend to put in run().
        consolidated = {}
        
        for paper in mock_results:
            source = paper.get('Source', 'Unknown')
            self.hunter.stats["identified"][source] = self.hunter.stats["identified"].get(source, 0) + 1
            
            title = paper.get('Title', '').strip()
            dedup_id = self.hunter.generate_slug(title)
            
            if dedup_id in consolidated:
                self.hunter.stats["duplicates_removed"] += 1
                if paper.get('Citations', 0) > consolidated[dedup_id].get('Citations', 0):
                    consolidated[dedup_id]['Citations'] = paper['Citations']
                continue
            
            # Simplified score and anchor check for test
            paper["Relevance_Score"] = self.hunter.calculate_score(title, paper.get('Abstract', ''))
            if paper["Relevance_Score"] >= self.hunter.settings["min_relevance_score"]:
                consolidated[dedup_id] = paper
                self.hunter.stats["included_final"] += 1
            else:
                self.hunter.stats["excluded_score"] += 1

        # Assertions
        self.assertEqual(len(consolidated), 1)
        self.assertEqual(consolidated[self.hunter.generate_slug("Duplicate Paper")]['Citations'], 20)
        self.assertEqual(self.hunter.stats["identified"]["SourceA"], 2)
        self.assertEqual(self.hunter.stats["identified"]["SourceB"], 1)
        self.assertEqual(self.hunter.stats["duplicates_removed"], 1)
        self.assertEqual(self.hunter.stats["excluded_score"], 1)
        self.assertEqual(self.hunter.stats["included_final"], 1)

    def test_prisma_math_low_score_duplicates(self):
        """Verify that identical low-score papers are counted as 1 excluded and 1 duplicate."""
        mock_results = [
            {"Title": "Low Score Paper", "Abstract": "X", "Source": "SourceA", "Citations": 0},
            {"Title": "Low Score Paper", "Abstract": "X", "Source": "SourceB", "Citations": 0}
        ]
        self.hunter.anchors = {"cat": ["X"]}
        self.hunter.settings["min_relevance_score"] = 10.0 # Force exclusion
        self.hunter.compiled_patterns = {"X": (re.compile(r"\bX\b"), 1.0)}
        self.hunter.anchor_patterns = {"X": re.compile(r"\bX\b")}

        # We will test the logic that should be in run()
        seen_ids = set()
        consolidated = {}
        self.hunter.stats = {"identified": {}, "duplicates_removed": 0, "excluded_score": 0, "included_final": 0}
        
        for paper in mock_results:
            source = paper.get('Source', 'Unknown')
            self.hunter.stats["identified"][source] = self.hunter.stats["identified"].get(source, 0) + 1
            dedup_id = self.hunter.generate_slug(paper["Title"])
            
            if dedup_id in seen_ids:
                self.hunter.stats["duplicates_removed"] += 1
                continue
            
            seen_ids.add(dedup_id)
            score = self.hunter.calculate_score(paper["Title"], paper["Abstract"])
            if score >= self.hunter.settings["min_relevance_score"]:
                consolidated[dedup_id] = paper
                self.hunter.stats["included_final"] += 1
            else:
                self.hunter.stats["excluded_score"] += 1
                
        self.assertEqual(self.hunter.stats["duplicates_removed"], 1)
        self.assertEqual(self.hunter.stats["excluded_score"], 1)

    def test_metadata_merging(self):
        """Verify metadata fields are merged correctly."""
        existing = {"Title": "T", "Abstract": "Short", "Citations": 10, "DOI": "", "Anchor_Category": "A1", "Tech_Category": "T1"}
        new = {"Title": "T", "Abstract": "Much Longer Abstract", "Citations": 20, "DOI": "10.1234", "Source": "S2"}
        
        # This will fail initially because the method doesn't exist
        self.hunter._merge_paper_metadata(existing, new, "A2", "T2")
        
        self.assertEqual(existing["Citations"], 20)
        self.assertEqual(existing["DOI"], "10.1234")
        self.assertEqual(existing["Abstract"], "Much Longer Abstract")
        self.assertIn("A1", existing["Anchor_Category"])
        self.assertIn("A2", existing["Anchor_Category"])
        self.assertIn("T1", existing["Tech_Category"])
        self.assertIn("T2", existing["Tech_Category"])

    def test_peer_review_detection(self):
        """Verify peer-review status detection heuristic."""
        papers = [
            {"Source": "Crossref", "Type": "journal-article", "expected": "Yes"},
            {"Source": "ArXiv", "Type": "preprint", "expected": "No (Preprint)"},
            {"Source": "OpenAlex", "Type": "article", "expected": "Yes"},
            {"Source": "OpenAlex", "Type": "proceedings-article", "expected": "Yes"},
            {"Source": "SemanticScholar", "Type": "JournalArticle", "expected": "Likely"},
            {"Source": "CORE", "Type": "journal", "expected": "Yes"},
            {"Source": "Unknown", "Type": "unknown", "expected": "N/A"}
        ]
        
        for p in papers:
            status = self.hunter.detect_peer_review(p)
            self.assertEqual(status, p["expected"], f"Failed for {p['Source']} ({p['Type']})")

    def test_venue_and_peer_review_merging(self):
        """Verify Venue and Peer_Reviewed are merged correctly."""
        existing = {
            "Title": "T", "Source": "ArXiv", "Venue": "ArXiv", 
            "Peer_Reviewed": "No (Preprint)", "DOI": ""
        }
        new = {
            "Title": "T", "Source": "Crossref", "Venue": "Nature", 
            "Type": "journal-article"
        }
        
        # detect_peer_review(new) should be "Yes"
        self.hunter._merge_paper_metadata(existing, new, "A", "T")
        
        self.assertEqual(existing["Venue"], "Nature")
        self.assertEqual(existing["Peer_Reviewed"], "Yes")

    def test_prisma_report_generation(self):
        """Verify that the PRISMA report is generated correctly."""
        self.hunter.stats = {
            "identified": {"ArXiv": 10, "Crossref": 20},
            "duplicates_removed": 5,
            "excluded_score": 10,
            "included_final": 15
        }
        
        timestamp = "TEST_TS"
        self.hunter.generate_prisma_report(timestamp)
        
        report_path = Path(self.test_dir) / f"FLUXO_PRISMA_{timestamp}.md"
        self.assertTrue(report_path.exists())
        
        content = report_path.read_text()
        self.assertIn("## 1. Breakdown by Source", content)
        self.assertIn("- **ArXiv:** 10", content)
        self.assertIn("- **Crossref:** 20", content)
        self.assertIn("Total Records Identified: 30", content)
        self.assertIn("Duplicates Removed: 5", content)
        self.assertIn("Final Records Included: 15", content)
        self.assertIn("```mermaid", content)
        self.assertIn("graph TD", content)

if __name__ == "__main__":
    unittest.main()
