import unittest
import json
import tempfile
import shutil
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

if __name__ == "__main__":
    unittest.main()
