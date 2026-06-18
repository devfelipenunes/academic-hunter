import unittest
from src.academic_hunter import AcademicHunter

class TestAcademicRigor(unittest.TestCase):
    def setUp(self):
        # Create instance with default config (or mock if needed)
        # For generate_slug, we don't necessarily need a valid config file if we don't call run()
        try:
            self.hunter = AcademicHunter()
        except FileNotFoundError:
            # Fallback if config.json is missing in current env
            import json
            from pathlib import Path
            config = {
                "settings": {"title_multiplier": 1.5, "score_precision": 1},
                "ancoras": {},
                "strings_tecnicas": {},
                "pesos_tecnicos": {}
            }
            Path('config.json').write_text(json.dumps(config))
            self.hunter = AcademicHunter()

    def test_generate_slug(self):
        """Verify title normalization into a slug."""
        title1 = "Blockchain & ISO 20022: A Survey!"
        title2 = "blockchain iso 20022 a survey"
        expected = "blockchainiso20022asurvey"
        
        self.assertEqual(self.hunter.generate_slug(title1), expected)
        self.assertEqual(self.hunter.generate_slug(title2), expected)

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
