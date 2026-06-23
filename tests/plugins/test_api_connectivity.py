import sys
from pathlib import Path
import time

# Add src to path if needed
sys.path.append(str(Path(__file__).parent))

try:
    from academic_hunter import AcademicHunter
except ImportError:
    from academic_hunter import AcademicHunter

import pytest
from academic_hunter import AcademicHunter

@pytest.fixture
def hunter():
    return AcademicHunter(use_cache=False)

@pytest.mark.integration
def test_arxiv_connectivity(hunter):
    results = hunter.fetch_arxiv(["AI"], ["machine learning"], limit=2)
    assert isinstance(results, list)

@pytest.mark.integration
def test_crossref_connectivity(hunter):
    results = hunter.fetch_crossref(["AI"], ["machine learning"], limit=2)
    assert isinstance(results, list)

@pytest.mark.integration
def test_semantic_scholar_connectivity(hunter):
    results = hunter.fetch_semantic_scholar(["AI"], ["machine learning"], limit=2)
    assert isinstance(results, list)

@pytest.mark.integration
def test_openalex_connectivity(hunter):
    results = hunter.fetch_openalex(["AI"], ["machine learning"], limit=2)
    assert isinstance(results, list)

@pytest.mark.integration
def test_core_ac_connectivity(hunter):
    results = hunter.fetch_core_ac(["AI"], ["machine learning"], limit=2)
    assert isinstance(results, list)
