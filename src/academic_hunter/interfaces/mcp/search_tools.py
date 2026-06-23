from academic_hunter import AcademicHunter

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
