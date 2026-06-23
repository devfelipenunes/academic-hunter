import pytest
from academic_hunter import AcademicHunter
import json
from pathlib import Path

def test_threaded_execution_integrity(tmp_path, monkeypatch):
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
    
    # Mock fetch methods to return a single dummy paper
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
    
    def mock_fetch(self, *args, **kwargs):
        # We need to return a NEW copy because _process_paper modifies it
        p = dummy_paper.copy()
        p["Source"] = self.__class__.__name__ # Distinguish by caller if possible
        return [p]

    monkeypatch.setattr(AcademicHunter, "fetch_arxiv", lambda *args, **kwargs: [dummy_paper.copy()])
    monkeypatch.setattr(AcademicHunter, "fetch_crossref", lambda *args, **kwargs: [dummy_paper.copy()])
    monkeypatch.setattr(AcademicHunter, "fetch_semantic_scholar", lambda *args, **kwargs: [dummy_paper.copy()])
    monkeypatch.setattr(AcademicHunter, "fetch_openalex", lambda *args, **kwargs: [dummy_paper.copy()])
    monkeypatch.setattr(AcademicHunter, "fetch_core_ac", lambda *args, **kwargs: [dummy_paper.copy()])
    monkeypatch.setattr(AcademicHunter, "fetch_dblp", lambda *args, **kwargs: [dummy_paper.copy()])
    monkeypatch.setattr(AcademicHunter, "fetch_doaj", lambda *args, **kwargs: [dummy_paper.copy()])

    # Run the pipeline
    hunter.run(limit_per_source=1)
    
    assert hunter.stats["included_final"] > 0
    assert len(hunter.consolidated_results) > 0
    # Duplicates should be handled by deduplication logic
    assert hunter.stats["duplicates_removed"] > 0 
