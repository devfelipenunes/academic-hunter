import argparse
import logging
from academic_hunter import AcademicHunter

def run_scraper():
    """Entry point for the main script."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    parser = argparse.ArgumentParser(description="Academic Hunter")
    parser.add_argument("--limit", type=int, default=None, help="Limit per source (overrides config)")
    args = parser.parse_args()
    
    hunter = AcademicHunter()
    if args.limit is not None:
        hunter.run(limit_per_source=args.limit)
    else:
        limit = hunter.config.settings.get("limit_per_query", 100)
        hunter.run(limit_per_source=limit)

if __name__ == "__main__":
    run_scraper()
