import argparse
from academic_hunter import AcademicHunter

def run_scraper():
    """Entry point para o script principal (antigo main.py)."""
    parser = argparse.ArgumentParser(description="Academic Hunter")
    parser.add_argument("--limit", type=int, default=5, help="Limit per source")
    args = parser.parse_args()
    
    hunter = AcademicHunter()
    hunter.run(limit_per_source=args.limit)

if __name__ == "__main__":
    run_scraper()
