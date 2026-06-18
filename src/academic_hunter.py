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
    from multiple APIs (ArXiv, Crossref, Semantic Scholar, CORE.ac.uk, OpenAlex).
    It filters results based on exact anchor matches and ranks them using a technical elite score.
    """
    
    def __init__(self, config_path: str = 'config.json', output_dir: str = 'results'):
        self.config_path = Path(config_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        self.load_config()
        self.setup_endpoints()
        
        self.stats = {
            "identified": {}, # Source: Count
            "duplicates_removed": 0,
            "excluded_score": 0,
            "included_final": 0
        }

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
        
        # Pre-compile patterns for anchors and technical strings
        self.anchor_patterns = {
            term: re.compile(rf'\b{re.escape(term.lower())}\b')
            for cat_list in self.anchors.values() for term in cat_list
        }
        self.tech_term_patterns = {
            term: re.compile(rf'\b{re.escape(term.lower())}\b')
            for cat_list in self.tech_strings.values() for term in cat_list
        }

    def setup_endpoints(self):
        """Initializes API endpoints."""
        self.arxiv_url = "http://export.arxiv.org/api/query?"
        self.crossref_url = "https://api.crossref.org/works"
        self.s2_url = "https://api.semanticscholar.org/graph/v1/paper/search"
        self.core_url = "https://api.core.ac.uk/v3/search/works"
        self.openalex_url = "https://api.openalex.org/works"

    def generate_slug(self, title: str) -> str:
        """Normalizes a title into a alphanumeric slug for duplicate detection."""
        if title is None: return ""
        return re.sub(r'\W+', '', str(title).lower())

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
            # Use pre-compiled pattern if available, otherwise compile on the fly
            pattern = self.anchor_patterns.get(term) or self.tech_term_patterns.get(term)
            if not pattern:
                pattern = re.compile(rf'\b{re.escape(term.lower())}\b')
                
            if pattern.search(text_lower):
                matches.add(term)
        return ", ".join(matches)

    def fetch_arxiv(self, anchors: List[str], tech_strings: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        """Fetches scholarly papers from ArXiv with flexible query logic."""
        anchor_group = ' OR '.join([f'all:"{t}"' for t in anchors])
        tech_group = ' OR '.join([f'all:{t}' for t in tech_strings])
        query = f"({anchor_group}) AND ({tech_group})"
        url = f"{self.arxiv_url}search_query={urllib.parse.quote(query)}&max_results={limit}"
        
        try:
            with urllib.request.urlopen(url) as response:
                root = ET.fromstring(response.read().decode('utf-8'))
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                return [{
                    "Title": e.find('atom:title', ns).text.strip().replace('\n', ' '),
                    "Abstract": e.find('atom:summary', ns).text.strip().replace('\n', ' '), 
                    "Year": e.find('atom:published', ns).text[:4],
                    "URL": e.find('atom:id', ns).text, 
                    "Source": "ArXiv",
                    "Citations": 0,
                    "Type": "preprint",
                    "Venue": "ArXiv"
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
                "DOI": i.get('DOI'),
                "Type": i.get('type'),
                "Venue": i.get('container-title', ["Unknown Venue"])[0]
            } for i in resp.get('message', {}).get('items', [])]
        except Exception as e:
            print(f"   [Crossref Error] {e}")
            return []

    def fetch_semantic_scholar(self, anchors: List[str], tech_strings: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        """Fetches papers from Semantic Scholar with keyword-based broad search."""
        query = f'{" ".join(anchors[:3])} {" ".join(tech_strings[:2])}' 
        start_year = self.settings.get('start_year', 2021)
        
        params = {
            "query": query, "limit": limit, "year": f"{start_year}-", 
            "fields": "title,abstract,url,year,citationCount,publicationTypes,externalIds,journal,venue"
        }
        
        try:
            resp = requests.get(self.s2_url, params=params, timeout=15).json()
            articles = []
            for i in resp.get('data', []):
                pub_types = i.get('publicationTypes', [])
                if not pub_types or not any(t in ['Editorial', 'News', 'Review'] for t in pub_types):
                    articles.append({
                        "Title": i.get('title'),
                        "Abstract": i.get('abstract') or "",
                        "Year": i.get('year'), 
                        "URL": i.get('url'),
                        "Source": "SemanticScholar",
                        "Citations": i.get('citationCount', 0), 
                        "DOI": i.get('externalIds', {}).get('DOI'),
                        "Type": ", ".join(pub_types) if pub_types else "N/A",
                        "Venue": i.get('journal', {}).get('name') or i.get('venue') or "Unknown Venue"
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

    def _merge_paper_metadata(self, existing: Dict, new: Dict, anchor_cat: str, tech_cat: str):
        """Enhances existing paper metadata with data from a duplicate."""
        if new.get('Citations', 0) > existing.get('Citations', 0):
            existing['Citations'] = new['Citations']
        
        if not existing.get('DOI') and new.get('DOI'):
            existing['DOI'] = new['DOI']
        
        if len(new.get('Abstract', '')) > len(existing.get('Abstract', '')):
            existing['Abstract'] = new['Abstract']
        
        # Merge Anchor Categories
        a_cats = set(existing.get('Anchor_Category', '').split(', '))
        a_cats.add(anchor_cat)
        existing['Anchor_Category'] = ', '.join(sorted(filter(None, a_cats)))

        # Merge Tech Categories
        t_cats = set(existing.get('Tech_Category', '').split(', '))
        t_cats.add(tech_cat)
        existing['Tech_Category'] = ', '.join(sorted(filter(None, t_cats)))

    def run(self, limit_per_source: int = 100):
        print(f"🚀 Initializing Academic Hunter V2 Pipeline...")
        consolidated_results = {} # Key: Title-Slug
        seen_ids = set() # Track ALL unique papers seen in this run
        
        # Reset stats for fresh run
        self.stats = {
            "identified": {},
            "duplicates_removed": 0,
            "excluded_score": 0,
            "included_final": 0
        }

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
                    # 1. Track Identification
                    source = paper.get('Source', 'Unknown')
                    self.stats["identified"][source] = self.stats["identified"].get(source, 0) + 1
                    
                    title = paper.get('Title', '').strip()
                    if not title: continue
                    
                    # 2. Deduplication by Title-Slug
                    dedup_id = self.generate_slug(title)
                    
                    if dedup_id in seen_ids:
                        self.stats["duplicates_removed"] += 1
                        if dedup_id in consolidated_results:
                            self._merge_paper_metadata(consolidated_results[dedup_id], paper, anchor_cat, tech_cat)
                        continue

                    seen_ids.add(dedup_id)

                    # 3. Anchor Filtering
                    full_text = f"{title} {paper.get('Abstract', '')}".lower()
                    matched_anchors = self.find_matching_terms(full_text, anchor_list)
                    if not matched_anchors: continue

                    # 4. Scoring and Exclusion
                    paper.update({
                        "Anchor_Category": anchor_cat,
                        "Matched_Anchors": matched_anchors,
                        "Tech_Category": tech_cat,
                        "Matched_Tech_Terms": self.find_matching_terms(full_text, tech_list),
                        "Relevance_Score": self.calculate_score(title, paper.get('Abstract', ''))
                    })
                    
                    if paper["Relevance_Score"] >= self.settings.get('min_relevance_score', 0):
                        consolidated_results[dedup_id] = paper
                        self.stats["included_final"] += 1
                    else:
                        self.stats["excluded_score"] += 1
                
                time.sleep(2)

        self.export_results(list(consolidated_results.values()))

    def export_results(self, results: List[Dict[str, Any]]):
        if not results:
            print("\n❌ No papers found.")
            return

        df = pd.DataFrame(results)
        df = df.sort_values(by=["Relevance_Score", "Citations"], ascending=[False, False])
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        csv_file = self.output_dir / f"academic_dataset_{timestamp}.csv"
        df.to_csv(csv_file, index=False, encoding='utf-8-sig')
        
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
        
        print(f"\n📊 PRISMA STATS:")
        print(f"   - Identified: {self.stats['identified']}")
        print(f"   - Duplicates Removed: {self.stats['duplicates_removed']}")
        print(f"   - Excluded (Score): {self.stats['excluded_score']}")
        print(f"   - Final Included: {self.stats['included_final']}")
        
        # Also write stats to the MD report
        with open(md_file, 'a', encoding='utf-8') as f:
            f.write("\n## PRISMA Flow Stats\n")
            f.write(f"- **Identified:** {json.dumps(self.stats['identified'])}\n")
            f.write(f"- **Duplicates Removed:** {self.stats['duplicates_removed']}\n")
            f.write(f"- **Excluded (Score):** {self.stats['excluded_score']}\n")
            f.write(f"- **Final Included:** {self.stats['included_final']}\n")

if __name__ == "__main__":
    hunter = AcademicHunter()
    hunter.run(limit_per_source=100)
