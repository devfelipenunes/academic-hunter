import urllib.request
import requests
import pandas as pd
import time
import json
import xml.etree.ElementTree as ET
import re
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
            
        self.compiled_patterns = {
            term: (re.compile(rf'\b{re.escape(term.lower())}\b'), weight)
            for term, weight in self.tech_weights.items()
        }

    def setup_endpoints(self):
        """Initializes API endpoints."""
        self.arxiv_url = "http://export.arxiv.org/api/query?"
        self.crossref_url = "https://api.crossref.org/works"
        self.s2_url = "https://api.semanticscholar.org/graph/v1/paper/search"
        self.core_url = "https://api.core.ac.uk/v3/search/works"
        self.openalex_url = "https://api.openalex.org/works"

    def calculate_score(self, title: str, abstract: str) -> float:
        score = 0.0
        title_lower = str(title).lower() if title else ""
        abstract_lower = str(abstract).lower() if abstract else ""
        
        multiplier = self.settings.get('title_multiplier', 1.5)
        precision = self.settings.get('score_precision', 1)
        
        for term, (pattern, weight) in self.compiled_patterns.items():
            # Check Title (bonus multiplier)
            if pattern.search(title_lower):
                score += (weight * multiplier)
            # Check Abstract (base weight) - using ELIF to avoid double counting same term
            elif pattern.search(abstract_lower):
                score += weight
                
        return round(score, precision)

    def find_matching_terms(self, text: str, terms_list: List[str]) -> str:
        """Returns a comma-separated string of terms from the list that appear in the text."""
        if not text: return ""
        text_lower = str(text).lower()
        matches = set()
        for term in terms_list:
            pattern = re.compile(rf'\b{re.escape(term.lower())}\b')
            if pattern.search(text_lower):
                matches.add(term)
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
        # Using a broader search logic combining terms
        query = f'{" ".join(anchors[:2])} {" ".join(tech_strings[:2])}' 
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
                        "Abstract": i.get('abstract') or "",
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

    def _decode_openalex_abstract(self, inverted_index):
        if not inverted_index: return ""
        try:
            max_pos = max(max(pos) for pos in inverted_index.values())
            words = [""] * (max_pos + 1)
            for word, positions in inverted_index.items():
                for pos in positions: words[pos] = word
            return " ".join(words).strip()
        except Exception:
            return ""

    def fetch_openalex(self, anchors: List[str], tech_strings: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        email = self.settings.get('user_email', 'academic_hunter@example.com')
        anchor_q = ' OR '.join([f'"{a}"' for a in anchors])
        tech_q = ' OR '.join([f'"{t}"' for t in tech_strings])
        query = f"({anchor_q}) AND ({tech_q})"
        
        url = self.openalex_url
        params = {
            "search": query,
            "mailto": email,
            "per_page": min(limit, 200),
            "filter": f"from_publication_date:{self.settings.get('start_year', 2021)}-01-01,type:article|proceedings-article"
        }
        
        try:
            resp = requests.get(url, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            articles = []
            for i in data.get('results', []):
                raw_doi = i.get('doi') or ""
                # More robust DOI normalization
                doi_clean = raw_doi.replace('https://doi.org/', '').replace('http://doi.org/', '').lower()
                
                abstract_text = self._decode_openalex_abstract(i.get('abstract_inverted_index', {}))
                
                articles.append({
                    "Title": i.get('display_name'),
                    "Abstract": abstract_text,
                    "Year": i.get('publication_year'),
                    "URL": i.get('doi') or i.get('id'),
                    "Source": "OpenAlex",
                    "Citations": i.get('cited_by_count', 0),
                    "DOI": doi_clean
                })
            return articles
        except Exception as e:
            print(f"   [OpenAlex Error] {e}")
            return []

    def run(self, limit_per_source: int = 100):
        print(f"🚀 Initializing Academic Hunter V2 Pipeline...")
        consolidated_results = {} # Key: DOI or Title-Slug
        
        for anchor_cat, anchor_list in self.anchors.items():
            for tech_cat, tech_list in self.tech_strings.items():
                print(f"\n📂 Mining: [{anchor_cat}] x [{tech_cat}]")
                
                raw_results = (
                    self.fetch_arxiv(anchor_list, tech_list, limit=limit_per_source) +
                    self.fetch_crossref(anchor_list, tech_list, limit=limit_per_source) +
                    self.fetch_semantic_scholar(anchor_list, tech_list, limit=limit_per_source) +
                    self.fetch_openalex(anchor_list, tech_list, limit=limit_per_source) +
                    self.fetch_core_ac(anchor_list, tech_list, limit=limit_per_source)
                )

                for paper in raw_results:
                    doi = paper.get('DOI', '').lower() if paper.get('DOI') else ''
                    title = paper.get('Title', '').strip()
                    if not title: continue
                    
                    # Deduplication ID
                    dedup_id = doi if doi else re.sub(r'\W+', '', title.lower())
                    
                    if dedup_id in consolidated_results:
                        # Update existing with more citations if found
                        if paper.get('Citations', 0) > consolidated_results[dedup_id].get('Citations', 0):
                            consolidated_results[dedup_id]['Citations'] = paper['Citations']
                        continue

                    full_text = f"{title} {paper.get('Abstract', '')}".lower()
                    matched_anchors = self.find_matching_terms(full_text, anchor_list)
                    if not matched_anchors: continue

                    paper.update({
                        "Anchor_Category": anchor_cat,
                        "Matched_Anchors": matched_anchors,
                        "Tech_Category": tech_cat,
                        "Matched_Tech_Terms": self.find_matching_terms(full_text, tech_list),
                        "Relevance_Score": self.calculate_score(title, paper.get('Abstract', ''))
                    })
                    
                    if paper["Relevance_Score"] >= self.settings.get('min_relevance_score', 0):
                        consolidated_results[dedup_id] = paper
                
                # Polite rate limiting to avoid API bans
                time.sleep(2)

        self.export_results(list(consolidated_results.values()))

    def export_results(self, results: List[Dict[str, Any]]):
        if not results:
            print("\n❌ No papers found.")
            return

        df = pd.DataFrame(results)
        df = df.sort_values(by=["Relevance_Score", "Citations"], ascending=[False, False])
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        
        # CSV
        csv_file = self.output_dir / f"academic_dataset_{timestamp}.csv"
        df.to_csv(csv_file, index=False, encoding='utf-8-sig')
        
        # Markdown Report
        md_file = self.output_dir / f"RELATORIO_ELITE_{timestamp}.md"
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(f"# Academic Hunter Elite Report - {timestamp}\n\n")
            for _, row in df.head(50).iterrows():
                f.write(f"### {row['Title']} (Score: {row['Relevance_Score']})\n")
                f.write(f"- **Year:** {row['Year']} | **Citations:** {row['Citations']}\n")
                f.write(f"- **Source:** {row['Source']} | **DOI:** {row['DOI']}\n")
                f.write(f"- **Anchors:** {row['Matched_Anchors']}\n")
                f.write(f"- [Link]({row['URL']})\n\n")

        print(f"\n💎 PIPELINE FINISHED!")
        print(f"📊 Dataset: {csv_file}")
        print(f"📝 Master Report: {md_file}")

if __name__ == "__main__":
    hunter = AcademicHunter()
    hunter.run(limit_per_source=100)
