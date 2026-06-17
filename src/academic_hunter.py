import urllib.request
import requests
import pandas as pd
import time
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any

class AcademicHunter:
    """
    AcademicHunter is an automated research tool that aggregates scholarly articles
    from multiple APIs (ArXiv, Crossref, Semantic Scholar, CORE.ac.uk).
    It filters results based on exact anchor matches and ranks them using a technical elite score.
    """
    
    def __init__(self, config_path: str = 'config.json', output_dir: str = 'results'):
        self.config_path = Path(config_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        self.load_config()
        self.setup_endpoints()

    def load_config(self):
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            full_config = json.load(f)
            self.settings = full_config.get('settings', {})
            self.anchors = full_config.get('ancoras', {})
            self.tech_strings = full_config.get('strings_tecnicas', {})
            self.tech_weights = full_config.get('pesos_tecnicos', {})

    def setup_endpoints(self):
        """Initializes API endpoints."""
        self.arxiv_url = "http://export.arxiv.org/api/query?"
        self.crossref_url = "https://api.crossref.org/works"
        self.s2_url = "https://api.semanticscholar.org/graph/v1/paper/search"
        self.core_url = "https://api.core.ac.uk/v3/search/works"

    def calculate_score(self, title: str, abstract: str) -> float:
        score = 0.0
        title_lower = str(title).lower() if title else ""
        abstract_lower = str(abstract).lower() if abstract else ""
        
        for term, weight in self.tech_weights.items():
            # Check Title (1.5x multiplier)
            if term in title_lower:
                score += (weight * 1.5)
            # Check Abstract (base weight)
            elif term in abstract_lower:
                score += weight
                
        return round(score, 1)

    def find_matching_terms(self, text: str, terms_list: List[str]) -> str:
        """Returns a comma-separated string of terms from the list that appear in the text."""
        if not text: return ""
        text_lower = str(text).lower()
        matches = set(term for term in terms_list if term.lower() in text_lower)
        return ", ".join(matches)

    def fetch_arxiv(self, anchors: List[str], tech_strings: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        """Fetches scholarly papers from ArXiv."""
        anchor_group = ' OR '.join([f'all:"{t}"' for t in anchors])
        tech_group = ' OR '.join([f'all:"{t}"' for t in tech_strings])
        query = f"({anchor_group}) AND ({tech_group})"
        url = f"{self.arxiv_url}search_query={urllib.parse.quote(query)}&max_results={limit}"
        
        try:
            with urllib.request.urlopen(url) as response:
                root = ET.fromstring(response.read().decode('utf-8'))
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                return [{
                    "Title": e.find('atom:title', ns).text.strip(),
                    "Abstract": e.find('atom:summary', ns).text.strip(), 
                    "Year": e.find('atom:published', ns).text[:4],
                    "URL": e.find('atom:id', ns).text, 
                    "Source": "ArXiv",
                    "Citations": 0
                } for e in root.findall('atom:entry', ns)]
        except Exception as e:
            print(f"   [ArXiv Error] {e}")
            return []

    def fetch_crossref(self, anchors: List[str], tech_strings: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        """Fetches peer-reviewed articles from Crossref."""
        anchor_group = ' '.join([f'"{t}"' for t in anchors])
        tech_group = ' '.join([f'"{t}"' for t in tech_strings])
        query = f"({anchor_group}) AND ({tech_group})"
        
        start_year = self.settings.get('start_year', 2021)
        user_email = self.settings.get('user_email', 'academic_hunter@example.com')
        
        params = {
            "query": query, "rows": limit, 
            "filter": f"type:journal-article,from-pub-date:{start_year}-01-01", 
            "mailto": user_email
        }
        
        try:
            resp = requests.get(self.crossref_url, params=params, timeout=15).json()
            return [{
                "Title": i.get('title', [""])[0],
                "Abstract": i.get('abstract', ""), 
                "Year": i.get('published-print', {}).get('date-parts', [[0]])[0][0] if 'published-print' in i else "N/A", 
                "URL": i.get('URL', ""),
                "Source": "Crossref",
                "Citations": i.get('is-referenced-by-count', 0),
                "DOI": i.get('DOI')
            } for i in resp.get('message', {}).get('items', [])]
        except Exception as e:
            print(f"   [Crossref Error] {e}")
            return []

    def fetch_semantic_scholar(self, anchors: List[str], tech_strings: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        """Fetches papers and citation counts from Semantic Scholar."""
        query = f"{anchors[0]} {tech_strings[0]}"
        start_year = self.settings.get('start_year', 2021)
        
        params = {
            "query": query, "limit": limit, "year": f"{start_year}-", 
            "fields": "title,abstract,url,year,citationCount,publicationTypes,externalIds"
        }
        
        try:
            resp = requests.get(self.s2_url, params=params, timeout=15).json()
            articles = []
            for i in resp.get('data', []):
                pub_types = i.get('publicationTypes', [])
                if pub_types and not any(t in ['Editorial', 'News', 'Review'] for t in pub_types):
                    articles.append({
                        "Title": i.get('title'),
                        "Abstract": i.get('abstract'),
                        "Year": i.get('year'), 
                        "URL": i.get('url'),
                        "Source": "SemanticScholar",
                        "Citations": i.get('citationCount', 0), 
                        "DOI": i.get('externalIds', {}).get('DOI')
                    })
            return articles
        except Exception as e:
            print(f"   [SemanticScholar Error] {e}")
            return []

    def fetch_core_ac(self, anchors: List[str], tech_strings: List[str], limit: int = 30) -> List[Dict[str, Any]]:
        """Fetches open access articles from CORE.ac.uk."""
        anchor_group = ' OR '.join([f'"{t}"' for t in anchors])
        tech_group = ' OR '.join([f'"{t}"' for t in tech_strings])
        query = f"title:({anchor_group}) AND abstract:({tech_group})"
        params = {"q": query, "limit": limit}
        
        try:
            resp = requests.get(self.core_url, params=params, timeout=20).json()
            return [{
                "Title": i.get('title'),
                "Abstract": i.get('abstract'),
                "Year": i.get('yearPublished'), 
                "URL": f"https://core.ac.uk/works/{i.get('id')}",
                "Source": "CORE",
                "Citations": 0,
                "DOI": i.get('doi')
            } for i in resp.get('results', [])]
        except Exception as e:
            print(f"   [CORE.ac.uk Error] {e}")
            return []

    def run(self, limit_per_source: int = None):
        """Executes the data mining pipeline across all configured endpoints."""
        if limit_per_source is None:
            limit_per_source = self.settings.get('limit_per_query', 100)
        
        min_score = self.settings.get('min_relevance_score', 0.0)

        print(f"🚀 Initializing Academic Hunter Pipeline...")
        consolidated_results = []
        seen_links = set()

        for anchor_cat, anchor_list in self.anchors.items():
            for tech_cat, tech_list in self.tech_strings.items():
                
                print(f"\n📂 Mining: [{anchor_cat}] x [{tech_cat}]")
                
                raw_results = (
                    self.fetch_arxiv(anchor_list, tech_list, limit=limit_per_source) +
                    self.fetch_crossref(anchor_list, tech_list, limit=limit_per_source) +
                    self.fetch_semantic_scholar(anchor_list, tech_list, limit=limit_per_source) +
                    self.fetch_core_ac(anchor_list, tech_list, limit=30)
                )
                
                valid_count = 0
                for paper in raw_results:
                    link = paper.get('URL')
                    if not link or link in seen_links: 
                        continue
                    
                    full_text = f"{paper.get('Title', '')} {paper.get('Abstract', '')}".lower()
                    
                    # Core Validation: The anchor MUST be present in the text
                    matched_anchors = self.find_matching_terms(full_text, anchor_list)
                    if not matched_anchors: 
                        continue
                    
                    score = self.calculate_score(paper.get('Title', ''), paper.get('Abstract', ''))
                    if score < min_score:
                        continue

                    paper.update({
                        "Anchor_Category": anchor_cat,
                        "Matched_Anchors": matched_anchors,
                        "Tech_Category": tech_cat,
                        "Matched_Tech_Terms": self.find_matching_terms(full_text, tech_list),
                        "Relevance_Score": score
                    })
                    
                    consolidated_results.append(paper)
                    seen_links.add(link)
                    valid_count += 1
                
                print(f"   ✨ {valid_count} scientific papers validated.")
                time.sleep(5) # Polite delay for APIs

        self.export_results(consolidated_results)

    def export_results(self, results: List[Dict[str, Any]]):
        """Exports the consolidated results to CSV and Markdown in the results/ folder."""
        if not results:
            print("\n❌ No academic papers found matching the criteria.")
            return

        df = pd.DataFrame(results)
        df = df.dropna(subset=['Title'])
        df = df.sort_values(by=["Relevance_Score", "Citations"], ascending=[False, False])
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        csv_file = self.output_dir / f"academic_dataset_{timestamp}.csv"
        df.to_csv(csv_file, index=False, encoding='utf-8-sig')
        
        print(f"\n💎 PIPELINE FINISHED!")
        print(f"📊 Dataset saved: {csv_file}")
        print(f"📚 Total validated papers: {len(df)}")

if __name__ == "__main__":
    hunter = AcademicHunter()
    hunter.run(limit_per_source=100)
