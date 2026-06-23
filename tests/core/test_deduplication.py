import unittest
import json
import tempfile
import shutil
from pathlib import Path
from academic_hunter import AcademicHunter

class TestDedupBug(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_path = Path(self.test_dir) / 'config.json'
        
        config = {
            "settings": {
                "title_multiplier": 1.5, 
                "score_precision": 1,
                "min_relevance_score": 5.0
            },
            "anchors": {"cat": ["anchor"]},
            "technical_strings": {"cat": ["tech"]},
            "technical_weights": {"anchor": 1.0, "tech": 10.0}
        }
        
        self.config_path.write_text(json.dumps(config))
        self.hunter = AcademicHunter(config_path=str(self.config_path), output_dir=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_promotion_of_previously_excluded_paper(self):
        """
        Verify that a paper previously excluded due to low score is included
        if a better version of it is found later.
        """
        # Version 1: Has anchor in abstract, but low score (1.0 < 5.0)
        paper1 = {
            "Title": "Research",
            "Abstract": "Nothing interesting here, just an anchor.",
            "Year": "2021",
            "URL": "url1",
            "Source": "Source1",
            "Citations": 0,
            "Type": "article",
            "Venue": "Venue1"
        }

        # Version 2: Same title, has tech in abstract, high score (10.0 >= 5.0)
        # MUST also match anchor to pass anchor filtering!
        paper2 = {
            "Title": "Research",
            "Abstract": "This is about tech and anchor.",
            "Year": "2021",
            "URL": "url2",
            "Source": "Source2",
            "Citations": 5,
            "Type": "article",
            "Venue": "Venue2"
        }

        # Mock fetch_arxiv to return paper1, and others to return nothing
        # Then mock fetch_crossref to return paper2 on the next iteration or something.
        # Actually, it's easier to mock all fetchers and control what they return.
        
        # We'll use a side_effect to return different results
        self.hunter.fetch_arxiv = lambda a, t, limit: [paper1] if "anchor" in a else []
        self.hunter.fetch_crossref = lambda a, t, limit: [paper2] if "anchor" in a else []
        self.hunter.fetch_semantic_scholar = lambda a, t, limit: []
        self.hunter.fetch_openalex = lambda a, t, limit: []
        self.hunter.fetch_core_ac = lambda a, t, limit: []
        self.hunter.fetch_dblp = lambda a, t, limit: []
        self.hunter.fetch_doaj = lambda a, t, limit: []
        
        # In the current implementation of run():
        # raw_results = fetch_arxiv + fetch_crossref + ...
        # If they are in the same raw_results list:
        # paper1 comes first, it is processed, seen_ids.add(), excluded_score += 1
        # paper2 comes second, it is in seen_ids, duplicates_removed += 1, continue.
        # RESULT: paper is lost.

        # Let's run it
        self.hunter.run(limit_per_source=10)

        # Verification
        print(f"Stats: {self.hunter.stats}")
        
        # If the bug is present, included_final will be 0 and excluded_score will be 1
        # If the bug is fixed, included_final should be 1, excluded_score should be 0, duplicates_removed should be 1
        
        self.assertEqual(self.hunter.stats["included_final"], 1, "Paper should have been promoted to included")
        self.assertEqual(self.hunter.stats["excluded_score"], 0, "Excluded score should have been decremented")
        self.assertEqual(self.hunter.stats["duplicates_removed"], 1, "Second version should still count as a duplicate removed")

    def test_promotion_from_anchor_mismatch(self):
        """
        Verify that a paper previously excluded due to anchor mismatch is included
        if a better version matches anchors and score.
        """
        # Version 1: NO anchor, NO tech. Fails anchor filtering.
        paper1 = {
            "Title": "Research",
            "Abstract": "Nothing interesting here.",
            "Year": "2021",
            "URL": "url1",
            "Source": "Source1",
            "Citations": 0,
            "Type": "article",
            "Venue": "Venue1"
        }

        # Version 2: Same title, has tech AND anchor.
        paper2 = {
            "Title": "Research",
            "Abstract": "This is about tech and anchor.",
            "Year": "2021",
            "URL": "url2",
            "Source": "Source2",
            "Citations": 5,
            "Type": "article",
            "Venue": "Venue2"
        }

        self.hunter.fetch_arxiv = lambda a, t, limit: [paper1] if "anchor" in a else []
        self.hunter.fetch_crossref = lambda a, t, limit: [paper2] if "anchor" in a else []
        self.hunter.fetch_semantic_scholar = lambda a, t, limit: []
        self.hunter.fetch_openalex = lambda a, t, limit: []
        self.hunter.fetch_core_ac = lambda a, t, limit: []
        self.hunter.fetch_dblp = lambda a, t, limit: []
        self.hunter.fetch_doaj = lambda a, t, limit: []
        
        self.hunter.run(limit_per_source=10)

        print(f"Stats (Anchor Mismatch Case): {self.hunter.stats}")
        
        # excluded_score should NOT be negative!
        self.assertGreaterEqual(self.hunter.stats["excluded_score"], 0)
        self.assertEqual(self.hunter.stats["included_final"], 1)

if __name__ == "__main__":
    unittest.main()
