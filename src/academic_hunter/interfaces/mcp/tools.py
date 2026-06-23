import json
from academic_hunter import AcademicHunter
from academic_hunter.core.infra.config import HunterConfig

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

def update_config(config_data_json: str) -> str:
    """
    Updates the search configurations.
    Receives a JSON string containing the new configurations. The format must respect the original structure.
    This should be used to inject optimized keywords based on the user's search intent before running run_search.
    """
    try:
        new_config = json.loads(config_data_json)
        config = HunterConfig()
        
        if "settings" in new_config: config.settings = new_config["settings"]
        if "anchors" in new_config: config.anchors = new_config["anchors"]
        if "technical_strings" in new_config: config.tech_strings = new_config["technical_strings"]
        if "technical_weights" in new_config: config.tech_weights = new_config["technical_weights"]
        
        config.save()
        return "config.json updated successfully!"
    except json.JSONDecodeError:
        return "Error: The provided string is not a valid JSON."
    except Exception as e:
        return f"Error saving config.json: {str(e)}"

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
