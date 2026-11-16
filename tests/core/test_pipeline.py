import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.append(str(Path(__file__).parent.parent / 'src'))

from academic_hunter import AcademicHunter
from academic_hunter.core.pipeline.manager import SearchPipeline


class TestAcademicHunterEnhancements(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config_dir = tempfile.mkdtemp(prefix="ah-test-config-")
        cls.test_config_path = os.path.join(cls.config_dir, 'test_config_enhancements.json')
        cls.config = {
            "settings": {
                "user_email": "test@example.com",
                "start_year": 2021,
                "min_relevance_score": 3.5,
                "title_multiplier": 1.5,
                "score_precision": 1,
            },
            "anchors": {
                "Pagamentos": ["Pix payment", "Zelle"]
            },
            "context_rules": {
                "drex": [
                    "cbdc", "digital currency", "payment", "central bank", "financial",
                    "banking", "ledger", "monetary", "real digital", "wholesale",
                    "retail", "liquidity", "transaction", "cross-border", "settlement",
                    "tokenization", "tokenized"
                ]
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
        shutil.rmtree(cls.config_dir, ignore_errors=True)

    def setUp(self):
        self.output_dir = tempfile.mkdtemp(prefix="ah-test-")
        self.hunter = AcademicHunter(
            config_path=self.test_config_path, output_dir=self.output_dir
        )

    def tearDown(self):
        shutil.rmtree(self.output_dir, ignore_errors=True)

    @patch('requests.get')
    def test_crossref_fallback_dates(self, mock_get):
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
        res = self.hunter.connectors["Crossref"].fetch(["Pix payment"], ["blockchain"])
        self.assertEqual(res[0]["Year"], 2023)

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
        res = self.hunter.connectors["Crossref"].fetch(["Pix payment"], ["blockchain"])
        self.assertEqual(res[0]["Year"], 2024)

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
        res = self.hunter.connectors["Crossref"].fetch(["Pix payment"], ["blockchain"])
        self.assertEqual(res[0]["Year"], 2022)

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
        res = self.hunter.connectors["Crossref"].fetch(["Pix payment"], ["blockchain"])
        self.assertEqual(res[0]["Year"], 2021)

    @patch('requests.get')
    def test_fetch_abstract_by_doi(self, mock_get):
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

        mock_get.side_effect = [None, None, mock_resp]
        mock_resp.json.return_value = {
            "message": {
                "abstract": "<jats:p>Crossref abstract text</jats:p>"
            }
        }
        abstract = self.hunter.fetch_abstract_by_doi("10.1000/crossref")
        self.assertEqual(abstract, "Crossref abstract text")

    @patch('requests.get')
    def test_enrich_metadata(self, mock_get):
        self.hunter.consolidated_results = {
            "emptyabstractpaper": {
                "Title": "Empty Abstract Paper",
                "Abstract": "",
                "DOI": "10.1000/enrich_me",
                "Citations": 5,
                "Source": "Crossref",
                "Relevance_Score": 7.5
            }
        }

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

        self.hunter.enrich_metadata()

        paper = self.hunter.consolidated_results["emptyabstractpaper"]
        self.assertEqual(paper["Abstract"], "Interoperability is good")
        self.assertTrue(paper["Relevance_Score"] > 0.0)

    def test_database_count_and_exclusion_tracking(self):
        paper = {
            "Title": "Paper A",
            "Abstract": "blockchain technology Zelle",
            "Source": "Crossref, OpenAlex, DBLP",
            "Citations": 0,
            "DOI": "10.1234/test",
            "Year": 2022
        }
        
        self.hunter._process_paper(paper, "Pagamentos", "Infra", ["Zelle"], ["blockchain"])
        
        self.assertEqual(self.hunter.stats["included_final"], 1)
        results = list(self.hunter.consolidated_results.values())
        
        import pandas as pd
        df = pd.DataFrame(results)
        df['Database_Count'] = df['Source'].apply(lambda x: len([s.strip() for s in x.split(',') if s.strip()]))
        
        self.assertEqual(df.loc[0, 'Database_Count'], 3)

        p_year = {
            "Title": "Paper Old",
            "Abstract": "blockchain technology Zelle",
            "Source": "ArXiv",
            "Year": 2018
        }
        self.hunter._process_paper(p_year, "Pagamentos", "Infra", ["Zelle"], ["blockchain"])
        self.assertEqual(self.hunter.stats["exclusions_by_source"]["ArXiv"]["year"], 1)

        p_anchor = {
            "Title": "Paper Out Of Scope",
            "Abstract": "blockchain technology",
            "Source": "ArXiv",
            "Year": 2023
        }
        self.hunter._process_paper(p_anchor, "Pagamentos", "Infra", ["Zelle"], ["blockchain"])
        self.assertEqual(self.hunter.stats["exclusions_by_source"]["ArXiv"]["anchor"], 1)

        prev_threshold = self.hunter.settings.get('min_relevance_score', 3.5)
        self.hunter.settings['min_relevance_score'] = 999.0
        p_score = {
            "Title": "Random Title Here",
            "Abstract": "Zelle protocol for a completely unrelated topic that no one cares about.",
            "Source": "ArXiv",
            "Year": 2023
        }
        self.hunter._process_paper(p_score, "Pagamentos", "Infra", ["Zelle"], ["blockchain"])
        self.assertEqual(self.hunter.stats["exclusions_by_source"]["ArXiv"]["score"], 1)
        self.hunter.settings['min_relevance_score'] = prev_threshold

    @patch('requests.get')
    def test_domain_pacing(self, mock_get):
        import time
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": []}
        mock_get.return_value = mock_resp

        self.hunter.last_request_by_domain = {}

        self.hunter._make_request("http://export.arxiv.org/api/query")
        t1 = time.time()
        
        self.hunter._make_request("http://export.arxiv.org/api/query")
        t2 = time.time()

        elapsed_arxiv = t2 - t1
        self.assertTrue(elapsed_arxiv >= 2.9, f"ArXiv requests were not spaced correctly: {elapsed_arxiv}s")

        self.hunter._make_request("https://api.crossref.org/works")
        t4 = time.time()
        
        self.hunter._make_request("https://api.crossref.org/works")
        t5 = time.time()
        
        elapsed_crossref = t5 - t4
        self.assertTrue(elapsed_crossref >= 1.4, f"Crossref requests were not spaced correctly: {elapsed_crossref}s")

    @patch('requests.get')
    def test_adaptive_pacing_escalation(self, mock_get):
        mock_resp_429 = MagicMock()
        mock_resp_429.status_code = 429
        
        mock_resp_200 = MagicMock()
        mock_resp_200.status_code = 200
        mock_resp_200.json.return_value = {"results": []}
        
        mock_get.side_effect = [mock_resp_429, mock_resp_200]
        
        import time
        real_sleep = time.sleep
        slept_times = []
        def mock_sleep(seconds):
            slept_times.append(seconds)
        time.sleep = mock_sleep
        
        try:
            self.hunter.pacing_delays = {"api.semanticscholar.org": 4.0}
            self.hunter._make_request("https://api.semanticscholar.org/graph/v1/paper/search")
            
            self.assertEqual(self.hunter.pacing_delays["api.semanticscholar.org"], 8.0)
            self.assertIn(30, slept_times)
        finally:
            time.sleep = real_sleep

    def test_optimized_query_flow(self):
        calls = []
        def mock_fetch(anchors, tech, limit):
            calls.append((anchors, tech))
            return []

        self.hunter.anchors["Pagamentos2"] = ["Zelle"]
        self.hunter.tech_strings["Infra2"] = ["interoperability"]
        
        calls.clear()
        SearchPipeline(self.hunter)._api_worker("DOAJ", mock_fetch, limit_per_source=5)
        self.assertEqual(len(calls), 2)

        calls.clear()
        SearchPipeline(self.hunter)._api_worker("Crossref", mock_fetch, limit_per_source=5)
        self.assertEqual(len(calls), 4)

    def test_prisma_consensus_and_rigor_stats(self):
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
        
        with open(report_path, encoding="utf-8") as f:
            content = f.read()
            
        self.assertIn("Database Consensus Overlap", content)
        self.assertIn("1 database | 1", content)
        self.assertIn("2 databases | 1", content)
        
        self.assertIn("Peer Review Rigor Distribution", content)
        self.assertIn("Yes | 1", content)
        self.assertIn("No (Preprint) | 1", content)
        
        report_path.unlink()

    def test_semantic_scholar_api_key_pacing(self):
        temp_cfg_path = os.path.join(self.output_dir, 'test_config_s2_key.json')
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
            
            s2_hunter = AcademicHunter(config_path=temp_cfg_path, output_dir=self.output_dir)
            
            self.assertEqual(s2_hunter.pacing_delays["api.semanticscholar.org"], 1.0)
            
            for name, conn in s2_hunter.connectors.items():
                self.assertEqual(conn.pacing_delays["api.semanticscholar.org"], 1.0)
        finally:
            if os.path.exists(temp_cfg_path):
                os.remove(temp_cfg_path)

    def test_drex_disambiguation(self):
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
        
        self.hunter.anchors = {"Pagamentos": ["Pix payment", "Zelle", "Drex"]}
        self.hunter.stats = {"identified": {}, "duplicates_removed": 0, "excluded_year": 0, "excluded_anchors": 0, "excluded_technical_score": 0, "included_final": 0}
        self.hunter.consolidated_results = {}
        self.hunter.seen_ids = set()
        
        self.hunter._process_paper(ml_paper, "Pagamentos", "Infra", ["Drex"], ["blockchain"])
        self.assertEqual(self.hunter.stats["excluded_anchors"], 1)
        self.assertEqual(self.hunter.stats["included_final"], 0)
        
        self.hunter.stats = {"identified": {}, "duplicates_removed": 0, "excluded_year": 0, "excluded_anchors": 0, "excluded_technical_score": 0, "included_final": 0}
        self.hunter.consolidated_results = {}
        self.hunter.seen_ids = set()
        self.hunter.settings["min_relevance_score"] = 0.0
        
        self.hunter._process_paper(fin_paper, "Pagamentos", "Infra", ["Drex"], ["blockchain"])
        self.assertEqual(self.hunter.stats["excluded_anchors"], 0)
        self.assertEqual(self.hunter.stats["included_final"], 1)

if __name__ == "__main__":
    unittest.main()
