import json
import requests
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from academic_hunter import AcademicHunter
from academic_hunter.core.infra.config import HunterConfig

class SearchConfigUpdate(BaseModel):
    settings: Optional[Dict] = Field(
        None, 
        description="Configurações gerais. Ex: {'min_relevance_score': 3.5, 'start_year': 2023}"
    )
    anchors: Optional[Dict[str, List[str]]] = Field(
        None, 
        description="Categorias principais de busca. Ex: {'Blockchain_Gov': ['CBDC', 'E-government', 'Smart Contracts']}"
    )
    technical_strings: Optional[Dict[str, List[str]]] = Field(
        None, 
        description="Termos técnicos secundários para filtrar. Ex: {'Consensus': ['Proof of Authority', 'Hyperledger']}"
    )
    technical_weights: Optional[Dict[str, float]] = Field(
        None, 
        description="Pesos para palavras específicas. Ex: {'cbdc': 5.0, 'hyperledger': 4.0}"
    )

def run_search(limit_per_source: int = 5) -> str:
    """
    Executes the consolidated academic search based on the keywords and weights from config.json.
    Use this tool only after having configured config.json with update_config (if necessary).
    """
    try:
        hunter = AcademicHunter()
        report_path = hunter.run(limit_per_source=limit_per_source)
        return f"Search completed successfully. Report generated at: {report_path}"
    except Exception as e:
        return f"Search error: {str(e)}"

def read_config() -> str:
    """
    Reads the current search configurations.
    Useful for inspecting the current search parameters (keywords, limit_per_source, year_start, etc) before updating them.
    """
    try:
        config = HunterConfig()
        data = {
            "settings": config.settings,
            "anchors": config.anchors,
            "technical_strings": config.tech_strings,
            "technical_weights": config.tech_weights
        }
        return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Error reading config: {str(e)}"

def update_config(config_update: SearchConfigUpdate) -> str:
    """
    Atualiza as configurações de busca do Hunter.
    Use esta ferramenta SEMPRE que o usuário pedir para pesquisar um novo tema.
    Traduza o pedido do usuário em 'anchors' e 'technical_strings' relevantes e atualize o config.json.
    """
    try:
        config = HunterConfig()
        
        if config_update.settings: config.settings.update(config_update.settings)
        if config_update.anchors: config.anchors = config_update.anchors
        if config_update.technical_strings: config.tech_strings = config_update.technical_strings
        if config_update.technical_weights: config.tech_weights = config_update.technical_weights
        
        config.save()
        return "Configurações atualizadas com sucesso! Você já pode usar a ferramenta run_search."
    except Exception as e:
        return f"Error saving config.json: {str(e)}"

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
