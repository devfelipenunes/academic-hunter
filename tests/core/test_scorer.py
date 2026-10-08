import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / 'src'))

import json

from academic_hunter import AcademicHunter


def test_score_logic(tmp_path):
    config = {
        "settings": {
            "title_multiplier": 2.0,
            "score_precision": 1
        },
        "technical_weights": {
            "blockchain": 5.0,
            "latency": 2.0
        }
    }

    config_path = tmp_path / 'test_config.json'
    with open(config_path, 'w') as f:
        json.dump(config, f)

    hunter = AcademicHunter(config_path=str(config_path), output_dir=str(tmp_path))

    score = hunter.calculate_score("Blockchain and Payments", "Some abstract")
    print(f"Test 1 (Title Bonus): Score {score} (Expected 10.0)")
    assert score == 10.0

    score = hunter.calculate_score("General Title", "Low latency is good")
    print(f"Test 2 (Abstract Base): Score {score} (Expected 2.0)")
    assert score == 2.0

    score = hunter.calculate_score("Blockchain Title", "Low latency")
    print(f"Test 3 (Combined): Score {score} (Expected 12.0)")
    assert score == 12.0

    score = hunter.calculate_score("Blockchain Title", "Blockchain abstract")
    print(f"Test 4 (ELIF - No Double Counting): Score {score} (Expected 10.0)")
    assert score == 10.0

    score = hunter.calculate_score("Title", "Improving latencies")
    print(f"Test 5 (Regex Boundary - No Match): Score {score} (Expected 0.0)")
    assert score == 0.0

    print("\n✅ All Task 3 verification tests PASSED!")
