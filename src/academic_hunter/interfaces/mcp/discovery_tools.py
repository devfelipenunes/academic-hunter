import requests
from academic_hunter import AcademicHunter

def explore_citation_graph(doi: str, direction: str = "citations") -> str:
    """
    Explore the citation graph of a paper using its DOI via Semantic Scholar.
    direction can be 'citations' (papers that cited this DOI) or 'references' (papers this DOI cited).
    Useful for snowballing research.
    """
    try:
        # Resolve DOI to Semantic Scholar ID format if necessary or use DOI: prefix
        paper_id = f"DOI:{doi}"
        
        if direction not in ["citations", "references"]:
            return "Error: direction must be 'citations' or 'references'."
            
        url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/{direction}?fields=title,year,authors&limit=10"
        
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return f"Error fetching from Semantic Scholar: {response.status_code} - {response.text}"
            
        data = response.json().get("data", [])
        if not data:
            return f"No {direction} found for DOI {doi}."
            
        results = [f"--- {direction.capitalize()} for {doi} ---"]
        for item in data:
            paper = item.get("citingPaper") if direction == "citations" else item.get("citedPaper")
            if not paper:
                continue
            title = paper.get("title", "Unknown Title")
            year = paper.get("year", "Unknown Year")
            results.append(f"- {title} ({year})")
            
        return "\n".join(results)
    except Exception as e:
        return f"Error exploring citation graph: {str(e)}"

def fetch_paper_by_doi(doi: str) -> str:
    """
    Fetches the abstract and metadata for a specific paper using its DOI.
    Useful when you need specific details about a single paper without running a full search.
    """
    try:
        hunter = AcademicHunter()
        abstract = hunter.fetch_abstract_by_doi(doi)
        if abstract:
            return f"Abstract found for DOI {doi}:\n{abstract}"
        return f"No abstract could be retrieved for DOI {doi}."
    except Exception as e:
        return f"Error fetching paper: {str(e)}"

def fetch_multiple_abstracts(dois: list[str]) -> str:
    """
    Fetches the abstracts for a list of DOIs.
    Useful for reading multiple papers at once to generate a literature review matrix or summary.
    """
    try:
        hunter = AcademicHunter()
        results = []
        for doi in dois:
            abstract = hunter.fetch_abstract_by_doi(doi)
            if abstract:
                results.append(f"--- Abstract for {doi} ---\n{abstract}\n")
            else:
                results.append(f"--- Abstract for {doi} ---\n[Not found]\n")
        return "\n".join(results)
    except Exception as e:
        return f"Error fetching multiple abstracts: {str(e)}"
