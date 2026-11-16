import json
import shutil
import tempfile
import unittest
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

        
        self.hunter.connectors["ArXiv"].fetch = lambda a, t, limit: [paper1] if "anchor" in a else []
        self.hunter.connectors["Crossref"].fetch = lambda a, t, limit: [paper2] if "anchor" in a else []
        self.hunter.connectors["Semantic Scholar"].fetch = lambda a, t, limit: []
        self.hunter.connectors["OpenAlex"].fetch = lambda a, t, limit: []
        self.hunter.connectors["CORE"].fetch = lambda a, t, limit: []
        self.hunter.connectors["DOAJ"].fetch = lambda a, t, limit: []
        

        self.hunter.run(limit_per_source=10)

        print(f"Stats: {self.hunter.stats}")

        self.assertEqual(len(self.hunter.consolidated_results), 1,
                         "The duplicate merge leaves exactly one paper")
        self.assertEqual(self.hunter.stats["included_final"], 1,
                         "The promoted paper is counted once, not once per source")
        self.assertEqual(self.hunter.stats["excluded_technical_score"], 0,
                         "No paper excluded after percentile re-ranking")

    def test_promotion_from_anchor_mismatch(self):
        """
        Verify that a paper previously excluded due to anchor mismatch is included
        if a better version matches anchors and score.
        """
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

        self.hunter.connectors["ArXiv"].fetch = lambda a, t, limit: [paper1] if "anchor" in a else []
        self.hunter.connectors["Crossref"].fetch = lambda a, t, limit: [paper2] if "anchor" in a else []
        self.hunter.connectors["Semantic Scholar"].fetch = lambda a, t, limit: []
        self.hunter.connectors["OpenAlex"].fetch = lambda a, t, limit: []
        self.hunter.connectors["CORE"].fetch = lambda a, t, limit: []
        self.hunter.connectors["DOAJ"].fetch = lambda a, t, limit: []
        
        self.hunter.run(limit_per_source=10)

        print(f"Stats (Anchor Mismatch Case): {self.hunter.stats}")
        
        self.assertGreaterEqual(self.hunter.stats["excluded_technical_score"], 0)
        self.assertEqual(self.hunter.stats["included_final"], 1)

if __name__ == "__main__":
    unittest.main()
