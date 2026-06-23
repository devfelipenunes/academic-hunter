import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / 'src'))

from academic_hunter import AcademicHunter
import json

def test_score_logic():
    # Mock config
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
    
    # Save mock config
    with open('test_config.json', 'w') as f:
        json.dump(config, f)
        
    try:
        hunter = AcademicHunter(config_path='test_config.json')
        
        # 1. Test multiplier in Title
        # blockchain (5.0) * multiplier (2.0) = 10.0
        score = hunter.calculate_score("Blockchain and Payments", "Some abstract")
        print(f"Test 1 (Title Bonus): Score {score} (Expected 10.0)")
        assert score == 10.0
        
        # 2. Test base weight in Abstract
        # latency (2.0)
        score = hunter.calculate_score("General Title", "Low latency is good")
        print(f"Test 2 (Abstract Base): Score {score} (Expected 2.0)")
        assert score == 2.0
        
        # 3. Test combined (Title + Abstract)
        # blockchain (5.0 * 2.0) + latency (2.0) = 12.0
        score = hunter.calculate_score("Blockchain Title", "Low latency")
        print(f"Test 3 (Combined): Score {score} (Expected 12.0)")
        assert score == 12.0
        
        # 4. Test ELIF (no double counting of SAME term)
        # blockchain in title (5.0 * 2.0) = 10.0 (even if also in abstract)
        score = hunter.calculate_score("Blockchain Title", "Blockchain abstract")
        print(f"Test 4 (ELIF - No Double Counting): Score {score} (Expected 10.0)")
        assert score == 10.0
        
        # 5. Test Regex Boundaries
        # 'latency' should match, 'latencies' should not (if using \b)
        score = hunter.calculate_score("Title", "Improving latencies")
        print(f"Test 5 (Regex Boundary - No Match): Score {score} (Expected 0.0)")
        assert score == 0.0
        
        print("\n✅ All Task 3 verification tests PASSED!")
    finally:
        Path('test_config.json').unlink(missing_ok=True)
 
if __name__ == "__main__":
    test_score_logic()
