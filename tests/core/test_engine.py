import json

from academic_hunter import AcademicHunter


def test_threaded_execution_integrity(tmp_path, stub_connector_fetch):
    config = {
        "settings": {"min_relevance_score": 0.5, "start_year": 2024},
        "anchors": {"test": ["artificial intelligence"]},
        "technical_strings": {"test": ["machine learning"]},
        "technical_weights": {"ai": 1.0, "learning": 0.5}
    }
    config_path = tmp_path / "config.json"
    with open(config_path, 'w') as f:
        json.dump(config, f)
        
    hunter = AcademicHunter(config_path=str(config_path), output_dir=str(tmp_path))
    
    dummy_paper = {
        "Title": "Artificial Intelligence Research",
        "Abstract": "AI and Machine Learning content.",
        "Year": "2024",
        "URL": "http://example.com",
        "Source": "Mock",
        "Citations": 10,
        "Type": "article",
        "Venue": "Mock Venue"
    }
    
    stub_connector_fetch([dummy_paper])

    hunter.run(limit_per_source=1)
    
    assert hunter.stats["included_final"] > 0
    assert len(hunter.consolidated_results) > 0
    assert hunter.stats["duplicates_removed"] > 0 
