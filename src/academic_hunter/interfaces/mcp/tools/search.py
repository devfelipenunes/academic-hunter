import os
import glob
from academic_hunter import AcademicHunter

def run_search(limit_per_source: int = None) -> str:
    """
    Executes the consolidated academic search based on the keywords and weights from config.json.
    Use this tool only after having configured config.json with update_config (if necessary).
    """
    try:
        hunter = AcademicHunter()
        if limit_per_source is None:
            limit_per_source = hunter.config.settings.get("limit_per_query", 100)
        report_path = hunter.run(limit_per_source=limit_per_source)
        return f"Search completed successfully. Report generated at: {report_path}"
    except Exception as e:
        return f"Search error: {str(e)}"

def read_latest_report() -> str:
    """
    Reads the latest Markdown report generated in the results/ folder.
    Useful for the agent to summarize the findings right after running run_search().
    """
    try:
        results_dir = os.path.join(os.getcwd(), "results")
        if not os.path.exists(results_dir):
            return "Error: No results directory found. Have you run a search yet?"
            
        md_files = glob.glob(os.path.join(results_dir, "*.md"))
        if not md_files:
            return "Error: No markdown reports found in results/."
            
        latest_file = max(md_files, key=os.path.getctime)
        with open(latest_file, "r", encoding="utf-8") as f:
            content = f.read()
            
        return content[:10000] if len(content) > 10000 else content
    except Exception as e:
        return f"Error reading latest report: {str(e)}"
