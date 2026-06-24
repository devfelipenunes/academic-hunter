import os
import glob
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

def read_latest_report() -> str:
    """
    Lê o relatório Markdown mais recente gerado na pasta results/.
    Útil para o agente resumir os resultados encontrados logo após rodar run_search().
    """
    try:
        results_dir = os.path.join(os.getcwd(), "results")
        if not os.path.exists(results_dir):
            return "Error: No results directory found. Have you run a search yet?"
            
        # Pega todos os arquivos .md e .csv, mas foca no Markdown Elite
        md_files = glob.glob(os.path.join(results_dir, "*.md"))
        if not md_files:
            return "Error: No markdown reports found in results/."
            
        latest_file = max(md_files, key=os.path.getctime)
        with open(latest_file, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Se for muito grande, retorna apenas o topo (ex: primeiros 10000 caracteres)
        return content[:10000] if len(content) > 10000 else content
    except Exception as e:
        return f"Error reading latest report: {str(e)}"
