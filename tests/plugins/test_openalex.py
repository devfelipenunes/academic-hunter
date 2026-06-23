import sys
from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock
import json
import os
import requests

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / 'src'))

from academic_hunter import AcademicHunter

class TestOpenAlex(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_config_path = 'test_config_task4.json'
        cls.config = {
            "settings": {
                "user_email": "test@example.com",
                "start_year": 2021
            },
            "anchors": {"cat1": ["anchor1"]},
            "technical_strings": {"cat2": ["tech1"]},
            "technical_weights": {"tech1": 1.0}
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
    def test_fetch_openalex_success(self, mock_get):
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "display_name": "Test Article",
                    "publication_year": 2023,
                    "doi": "https://doi.org/10.1234/test.123",
                    "id": "https://openalex.org/W123",
                    "cited_by_count": 10
                }
            ]
        }
        mock_get.return_value = mock_response

        results = self.hunter.fetch_openalex(["anchor1"], ["tech1"])
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["Title"], "Test Article")
        self.assertEqual(results[0]["DOI"], "10.1234/test.123") # Normalized
        self.assertEqual(results[0]["URL"], "https://doi.org/10.1234/test.123")

    @patch('requests.get')
    def test_fetch_openalex_no_doi(self, mock_get):
        # Mock response without DOI
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "display_name": "No DOI Article",
                    "publication_year": 2022,
                    "doi": None,
                    "id": "https://openalex.org/W456",
                    "cited_by_count": 5
                }
            ]
        }
        mock_get.return_value = mock_response

        results = self.hunter.fetch_openalex(["anchor1"], ["tech1"])
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["DOI"], "")
        self.assertEqual(results[0]["URL"], "https://openalex.org/W456")

    @patch('requests.get')
    def test_fetch_openalex_http_error(self, mock_get):
        # Mock HTTP error
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Client Error")
        mock_get.return_value = mock_response
        
        results = self.hunter.fetch_openalex(["anchor1"], ["tech1"])
        self.assertEqual(results, [])

    @patch('requests.get')
    def test_fetch_openalex_invalid_json(self, mock_get):
        # Mock invalid JSON
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_response
        
        results = self.hunter.fetch_openalex(["anchor1"], ["tech1"])
        self.assertEqual(results, [])

if __name__ == "__main__":
    import requests # Ensure requests is available for the exception
    unittest.main()
