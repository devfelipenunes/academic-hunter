from unittest.mock import patch, MagicMock
from academic_hunter.interfaces.mcp.discovery_tools import explore_citation_graph, fetch_paper_by_doi, fetch_multiple_abstracts

@patch("academic_hunter.interfaces.mcp.discovery_tools.requests.get")
def test_explore_citation_graph(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [
            {"citingPaper": {"paperId": "123", "title": "Citing Paper A", "year": 2024}}
        ]
    }
    mock_get.return_value = mock_response
    
    result = explore_citation_graph(doi="10.1000/182", direction="citations")
    
    assert "Citing Paper A" in result
    assert "2024" in result
    mock_get.assert_called_once()

@patch("academic_hunter.interfaces.mcp.discovery_tools.AcademicHunter")
def test_fetch_paper_by_doi(mock_hunter_class):
    mock_instance = MagicMock()
    mock_instance.fetch_abstract_by_doi.return_value = "This is a test abstract."
    mock_hunter_class.return_value = mock_instance
    
    result = fetch_paper_by_doi("10.1234/test")
    assert "This is a test abstract." in result

@patch("academic_hunter.interfaces.mcp.discovery_tools.AcademicHunter")
def test_fetch_multiple_abstracts(mock_hunter_class):
    mock_instance = MagicMock()
    # Retorna abstracts diferentes baseados no DOI
    mock_instance.fetch_abstract_by_doi.side_effect = lambda doi: f"Abstract for {doi}"
    mock_hunter_class.return_value = mock_instance
    
    dois = ["10.1/A", "10.2/B"]
    result = fetch_multiple_abstracts(dois)
    
    assert "Abstract for 10.1/A" in result
    assert "Abstract for 10.2/B" in result
    assert mock_instance.fetch_abstract_by_doi.call_count == 2
