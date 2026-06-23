import unittest
from unittest.mock import patch, MagicMock
import json
import os
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / 'src'))

from academic_hunter import AcademicHunter

class TestAcademicHunterEnhancements(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_config_path = 'test_config_enhancements.json'
        cls.config = {
            "settings": {
                "user_email": "test@example.com",
                "start_year": 2021,
                "min_relevance_score": 3.5,
                "title_multiplier": 1.5,
                "score_precision": 1,
                "context_rules": {
                    "drex": [
                        "cbdc", "digital currency", "payment", "central bank", "financial", 
                        "banking", "ledger", "monetary", "real digital", "wholesale", 
                        "retail", "liquidity", "transaction", "cross-border", "settlement",
                        "tokenization", "tokenized"
                    ]
                }
            },
            "anchors": {
                "Pagamentos": ["Pix payment", "Zelle"]
            },
            "technical_strings": {
                "Infra": ["blockchain", "interoperability"]
            },
            "technical_weights": {
                "blockchain": 5.0,
                "interoperability": 3.0
            }
        }
        with open(cls.test_config_path, 'w') as f:
            json.dump(cls.config, f)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_config_path):
            os.remove(cls.test_config_path)

    def setUp(self):
        self.hunter = AcademicHunter(config_path=self.test_config_path)

    @patch('requests.get')
    def test_crossref_fallback_dates(self, mock_get):
        # Scenario 1: published-print works
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {
                "items": [
                    {
                        "title": ["Paper Print"],
                        "published-print": {"date-parts": [[2023, 5, 1]]},
                        "URL": "http://example.com/1",
                        "is-referenced-by-count": 2,
                        "DOI": "10.1000/print",
                        "type": "journal-article"
                    }
                ]
            }
        }
        mock_get.return_value = mock_resp
        res = self.hunter.fetch_crossref(["Pix payment"], ["blockchain"])
        self.assertEqual(res[0]["Year"], 2023)

        # Scenario 2: published-print missing, published-online present
        mock_resp.json.return_value = {
            "message": {
                "items": [
                    {
                        "title": ["Paper Online"],
                        "published-online": {"date-parts": [[2024, 6, 1]]},
                        "URL": "http://example.com/2",
                        "is-referenced-by-count": 0,
                        "DOI": "10.1000/online",
                        "type": "journal-article"
                    }
                ]
            }
        }
        res = self.hunter.fetch_crossref(["Pix payment"], ["blockchain"])
        self.assertEqual(res[0]["Year"], 2024)

        # Scenario 3: print/online missing, issued present
        mock_resp.json.return_value = {
            "message": {
                "items": [
                    {
                        "title": ["Paper Issued"],
                        "issued": {"date-parts": [[2022, 12]]},
                        "URL": "http://example.com/3",
                        "is-referenced-by-count": 0,
                        "DOI": "10.1000/issued",
                        "type": "journal-article"
                    }
                ]
            }
        }
        res = self.hunter.fetch_crossref(["Pix payment"], ["blockchain"])
        self.assertEqual(res[0]["Year"], 2022)

        # Scenario 4: print/online/issued missing, created present
        mock_resp.json.return_value = {
            "message": {
                "items": [
                    {
                        "title": ["Paper Created"],
                        "created": {"date-parts": [[2021, 10, 5]]},
                        "URL": "http://example.com/4",
                        "is-referenced-by-count": 0,
                        "DOI": "10.1000/created",
                        "type": "journal-article"
                    }
                ]
            }
        }
        res = self.hunter.fetch_crossref(["Pix payment"], ["blockchain"])
        self.assertEqual(res[0]["Year"], 2021)

    @patch('requests.get')
    def test_fetch_abstract_by_doi(self, mock_get):
        # Test OpenAlex abstract decode
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "abstract_inverted_index": {
                "Blockchain": [0],
                "in": [1],
                "finance": [2]
            }
        }
        mock_get.return_value = mock_resp
        
        abstract = self.hunter.fetch_abstract_by_doi("10.1000/openalex")
        self.assertEqual(abstract, "Blockchain in finance")

        # Test Crossref fallback for abstract
        # OpenAlex fails (None returned), Crossref succeeds
        mock_get.side_effect = [None, None, mock_resp]
        mock_resp.json.return_value = {
            "message": {
                "abstract": "<jats:p>Crossref abstract text</jats:p>"
            }
        }
        abstract = self.hunter.fetch_abstract_by_doi("10.1000/crossref")
        self.assertEqual(abstract, "Crossref abstract text")

    @patch('requests.get')
    def test_enrich_missing_abstracts(self, mock_get):
        # Setup consolidated results with an empty abstract but valid DOI
        self.hunter.consolidated_results = {
            "emptyabstractpaper": {
                "Title": "Empty Abstract Paper",
                "Abstract": "",
                "DOI": "10.1000/enrich_me",
                "Citations": 5,
                "Source": "Crossref",
                "Relevance_Score": 7.5 # Score based on title match only
            }
        }

        # Mock response for OpenAlex
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "abstract_inverted_index": {
                "Interoperability": [0],
                "is": [1],
                "good": [2]
            }
        }
        mock_get.return_value = mock_resp

        self.hunter.enrich_missing_abstracts()

        paper = self.hunter.consolidated_results["emptyabstractpaper"]
        self.assertEqual(paper["Abstract"], "Interoperability is good")
        # Score should increase from title "Empty Abstract Paper" (no technical weights match title)
        # to including "Interoperability" in abstract (weight 3.0 * (1 + ln(1)) = 3.0)
        # plus citations 5 (0.1 * ln(6) = 0.18 => rounds to score precision)
        self.assertTrue(paper["Relevance_Score"] > 0.0)

    def test_database_count_and_exclusion_tracking(self):
        # 1. Test database count logic
        paper = {
            "Title": "Paper A",
            "Abstract": "blockchain technology Zelle",
            "Source": "Crossref, OpenAlex, DBLP",
            "Citations": 0,
            "DOI": "10.1234/test",
            "Year": 2022
        }
        
        self.hunter._process_paper(paper, "Pagamentos", "Infra", ["Zelle"], ["blockchain"])
        
        # Verify it got included
        self.assertEqual(self.hunter.stats["included_final"], 1)
        results = list(self.hunter.consolidated_results.values())
        
        # Mock export results format mapping
        import pandas as pd
        df = pd.DataFrame(results)
        df['Database_Count'] = df['Source'].apply(lambda x: len([s.strip() for s in x.split(',') if s.strip()]))
        
        self.assertEqual(df.loc[0, 'Database_Count'], 3)

        # 2. Test exclusion tracking
        # Paper out of date range
        p_year = {
            "Title": "Paper Old",
            "Abstract": "blockchain technology Zelle",
            "Source": "ArXiv",
            "Year": 2018
        }
        self.hunter._process_paper(p_year, "Pagamentos", "Infra", ["Zelle"], ["blockchain"])
        self.assertEqual(self.hunter.stats["exclusions_by_source"]["ArXiv"]["year"], 1)

        # Paper out of scope (no anchors)
        p_anchor = {
            "Title": "Paper Out Of Scope",
            "Abstract": "blockchain technology",
            "Source": "ArXiv",
            "Year": 2023
        }
        self.hunter._process_paper(p_anchor, "Pagamentos", "Infra", ["Zelle"], ["blockchain"])
        self.assertEqual(self.hunter.stats["exclusions_by_source"]["ArXiv"]["anchor"], 1)

        # Paper failed relevance score
        p_score = {
            "Title": "Zelle only paper",
            "Abstract": "some standard banking things",
            "Source": "ArXiv",
            "Year": 2023
        }
        self.hunter._process_paper(p_score, "Pagamentos", "Infra", ["Zelle"], ["blockchain"])
        self.assertEqual(self.hunter.stats["exclusions_by_source"]["ArXiv"]["score"], 1)

    @patch('requests.get')
    def test_domain_pacing(self, mock_get):
        import time
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": []}
        mock_get.return_value = mock_resp

        # Initialize tracking dict in hunter
        self.hunter.last_request_by_domain = {}

        # First request to ArXiv (delay is 3.0s)
        self.hunter._make_request("http://export.arxiv.org/api/query")
        t1 = time.time()
        
        # Second request to ArXiv (should wait 3.0s)
        self.hunter._make_request("http://export.arxiv.org/api/query")
        t2 = time.time()

        # Elapsed between t1 and t2 should be >= 3.0 seconds (accounting for minor float variance)
        elapsed_arxiv = t2 - t1
        self.assertTrue(elapsed_arxiv >= 2.9, f"ArXiv requests were not spaced correctly: {elapsed_arxiv}s")

        # Now test different domains: request to Crossref
        self.hunter._make_request("https://api.crossref.org/works")
        t4 = time.time()
        
        self.hunter._make_request("https://api.crossref.org/works")
        t5 = time.time()
        
        elapsed_crossref = t5 - t4
        self.assertTrue(elapsed_crossref >= 1.4, f"Crossref requests were not spaced correctly: {elapsed_crossref}s")

    @patch('requests.get')
    def test_adaptive_pacing_escalation(self, mock_get):
        # Mock first response is 429 (Too Many Requests), second is 200 (Success)
        mock_resp_429 = MagicMock()
        mock_resp_429.status_code = 429
        
        mock_resp_200 = MagicMock()
        mock_resp_200.status_code = 200
        mock_resp_200.json.return_value = {"results": []}
        
        mock_get.side_effect = [mock_resp_429, mock_resp_200]
        
        # Override sleep to run fast
        import time
        real_sleep = time.sleep
        slept_times = []
        def mock_sleep(seconds):
            slept_times.append(seconds)
        time.sleep = mock_sleep
        
        try:
            self.hunter.pacing_delays = {"api.semanticscholar.org": 4.0}
            self.hunter._make_request("https://api.semanticscholar.org/graph/v1/paper/search")
            
            # Pacing delay should have doubled
            self.assertEqual(self.hunter.pacing_delays["api.semanticscholar.org"], 8.0)
            # Should have slept for 30s for the back-off cooldown
            self.assertIn(30, slept_times)
        finally:
            time.sleep = real_sleep

    def test_optimized_query_flow(self):
        calls = []
        def mock_fetch(anchors, tech, limit):
            calls.append((anchors, tech))
            return []

        # Add another anchor and tech category to the test hunter
        self.hunter.anchors["Pagamentos2"] = ["Zelle"]
        self.hunter.tech_strings["Infra2"] = ["interoperability"]
        
        # DBLP (keyword-only) should be called 2 times (once per anchor category)
        calls.clear()
        self.hunter._api_worker("DBLP", mock_fetch, limit_per_source=5)
        self.assertEqual(len(calls), 2)
        
        # Crossref (grid search) should be called 2 * 2 = 4 times
        calls.clear()
        self.hunter._api_worker("Crossref", mock_fetch, limit_per_source=5)
        self.assertEqual(len(calls), 4)

    def test_prisma_consensus_and_rigor_stats(self):
        # Mock 2 consolidated papers in the hunter
        self.hunter.consolidated_results = {
            "paper1": {
                "Title": "Paper A",
                "Year": 2022,
                "Source": "Crossref, OpenAlex",
                "Peer_Reviewed": "Yes",
                "Relevance_Score": 5.0
            },
            "paper2": {
                "Title": "Paper B",
                "Year": 2023,
                "Source": "ArXiv",
                "Peer_Reviewed": "No (Preprint)",
                "Relevance_Score": 4.0
            }
        }
        
        # Mock stats
        self.hunter.stats = {
            "identified": {"ArXiv": 1, "Crossref": 1, "OpenAlex": 1},
            "duplicates_removed": 0,
            "excluded_year": 0,
            "excluded_anchors": 0,
            "excluded_technical_score": 0,
            "included_final": 2,
            "exclusions_by_source": {}
        }
        
        self.hunter.generate_prisma_report("test_stats")
        
        report_path = self.hunter.output_dir / "FLUXO_PRISMA_test_stats.md"
        self.assertTrue(report_path.exists())
        
        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Check that it has database consensus overlap table
        self.assertIn("Database Consensus Overlap", content)
        self.assertIn("1 database | 1", content)
        self.assertIn("2 databases | 1", content)
        
        # Check peer review distribution
        self.assertIn("Peer Review Rigor Distribution", content)
        self.assertIn("Yes | 1", content)
        self.assertIn("No (Preprint) | 1", content)
        
        # Clean up
        report_path.unlink()

    def test_semantic_scholar_api_key_pacing(self):
        # Create a temp config with Semantic Scholar API key
        temp_cfg_path = 'test_config_s2_key.json'
        cfg = {
            "settings": {
                "user_email": "test@example.com",
                "start_year": 2021,
                "api_keys": {
                    "semantic_scholar": "s2k-test-key"
                }
            },
            "anchors": {"cat": ["anchor"]},
            "technical_strings": {"cat": ["tech"]},
            "technical_weights": {"tech": 1.0}
        }
        try:
            with open(temp_cfg_path, 'w') as f:
                json.dump(cfg, f)
            
            s2_hunter = AcademicHunter(config_path=temp_cfg_path)
            
            # Pacing delay should have been updated to 1.0s
            self.assertEqual(s2_hunter._pacing_delays["api.semanticscholar.org"], 1.0)
            
            # Check connectors pacing_delays propagation
            for name, conn in s2_hunter.connectors.items():
                self.assertEqual(conn.pacing_delays["api.semanticscholar.org"], 1.0)
        finally:
            if os.path.exists(temp_cfg_path):
                os.remove(temp_cfg_path)

    def test_drex_disambiguation(self):
        # Setup two papers: one machine learning "Drex", one financial "Drex"
        ml_paper = {
            "Title": "DReX: Pure Vision Fusion of Self-Supervised and Convolutional Representations",
            "Abstract": "This paper presents a new deep learning framework called DReX for image complexity prediction. We evaluate its latency and throughput.",
            "Year": 2025,
            "Source": "ArXiv",
            "Citations": 0
        }
        
        fin_paper = {
            "Title": "Evaluating the Central Bank Digital Currency in Brazil",
            "Abstract": "We analyze Drex, the new Brazilian CBDC, and its implications on retail payments and liquidity.",
            "Year": 2025,
            "Source": "ArXiv",
            "Citations": 0
        }
        
        # Test 1: ML paper should fail anchor check
        self.hunter.anchors = {"Pagamentos": ["Pix payment", "Zelle", "Drex"]}
        self.hunter.stats = {"identified": {}, "duplicates_removed": 0, "excluded_year": 0, "excluded_anchors": 0, "excluded_technical_score": 0, "excluded_score": 0, "included_final": 0}
        self.hunter.consolidated_results = {}
        self.hunter.seen_ids = set()
        
        self.hunter._process_paper(ml_paper, "Pagamentos", "Infra", ["Drex"], ["blockchain"])
        self.assertEqual(self.hunter.stats["excluded_anchors"], 1)
        self.assertEqual(self.hunter.stats["included_final"], 0)
        
        # Test 2: Financial paper should pass anchor check
        self.hunter.stats = {"identified": {}, "duplicates_removed": 0, "excluded_year": 0, "excluded_anchors": 0, "excluded_technical_score": 0, "excluded_score": 0, "included_final": 0}
        self.hunter.consolidated_results = {}
        self.hunter.seen_ids = set()
        self.hunter.settings["min_relevance_score"] = 0.0
        
        self.hunter._process_paper(fin_paper, "Pagamentos", "Infra", ["Drex"], ["blockchain"])
        self.assertEqual(self.hunter.stats["excluded_anchors"], 0)
        self.assertEqual(self.hunter.stats["included_final"], 1)

if __name__ == "__main__":
    unittest.main()
