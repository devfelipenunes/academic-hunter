import urllib.request
import requests
import pandas as pd
import time
import json
import xml.etree.ElementTree as ET
import re
import threading
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
        
        self.lock = threading.Lock()
        self.consolidated_results = {} # Key: Title-Slug or DOI
        self.seen_ids = set() # Track ALL unique papers seen in this run
        
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
                
                articles = []
                for e in root.findall('atom:entry', ns):
                    title_elem = e.find('atom:title', ns)
                    summary_elem = e.find('atom:summary', ns)
                    published_elem = e.find('atom:published', ns)
                    id_elem = e.find('atom:id', ns)
                    
                    articles.append({
                        "Title": title_elem.text.strip().replace('\n', ' ') if title_elem is not None and title_elem.text else "N/A",
                        "Abstract": summary_elem.text.strip().replace('\n', ' ') if summary_elem is not None and summary_elem.text else "", 
                        "Year": published_elem.text[:4] if published_elem is not None and published_elem.text else "N/A",
                        "URL": id_elem.text if id_elem is not None and id_elem.text else "", 
                        "Source": "ArXiv",
                        "Citations": 0,
                        "Type": "preprint",
                        "Venue": "ArXiv"
                    })
                return articles
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
        
        data = self._make_request(self.crossref_url, params=params, timeout=15)
        if not data:
            return []
            
        try:
            articles = []
            for i in data.get('message', {}).get('items', []):
                titles = i.get('title', [])
                title = titles[0] if titles else "Unknown Title"
                
                venues = i.get('container-title', [])
                venue = venues[0] if venues else "Unknown Venue"
                
                # Safe year extraction
                published_print = i.get('published-print', {})
                date_parts = published_print.get('date-parts', [])
                year = date_parts[0][0] if date_parts and date_parts[0] else "N/A"
                
                articles.append({
                    "Title": title,
                    "Abstract": i.get('abstract', ""), 
                    "Year": year, 
                    "URL": i.get('URL', ""),
                    "Source": "Crossref",
                    "Citations": i.get('is-referenced-by-count', 0),
                    "DOI": i.get('DOI'),
                    "Type": i.get('type', "journal-article"),
                    "Venue": venue
                })
            return articles
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
        
        data = self._make_request(self.s2_url, params=params, timeout=15)
        if not data:
            return []
            
        try:
            articles = []
            for i in data.get('data', []):
                pub_types = i.get('publicationTypes', [])
                if not pub_types or not any(t in ['Editorial', 'News', 'Review'] for t in pub_types):
                    # Safe navigation for Semantic Scholar metadata
                    journal_info = i.get('journal') or {}
                    venue_name = journal_info.get('name') or i.get('venue') or "Unknown Venue"

                    articles.append({
                        "Title": i.get('title', "Unknown Title"),
                        "Abstract": i.get('abstract') or "",
                        "Year": i.get('year', "N/A"), 
                        "URL": i.get('url', ""),
                        "Source": "SemanticScholar",
                        "Citations": i.get('citationCount', 0), 
                        "DOI": i.get('externalIds', {}).get('DOI'),
                        "Type": ", ".join(pub_types) if pub_types else "N/A",
                        "Venue": venue_name
                    })
            return articles
        except Exception as e:
            print(f"   [SemanticScholar Error] {e}")
            return []

    def _make_request(self, url: str, params: Dict[str, Any] = None, timeout: int = 20, max_retries: int = 5) -> Any:
        """Helper to make HTTP requests with aggressive exponential backoff for 429 errors."""
        for attempt in range(max_retries):
            try:
                resp = requests.get(url, params=params, timeout=timeout)
                if resp.status_code == 429:
                    # More aggressive backoff: 10s, 20s, 40s, 80s, 160s
                    wait_time = (2 ** attempt) * 10
                    print(f"   [Rate Limit] HTTP 429 from {url}. Waiting {wait_time}s (Attempt {attempt+1}/{max_retries})...")
                    time.sleep(wait_time)
                    continue
                
                if resp.status_code != 200:
                    return None
                
                return resp.json()
            except Exception:
                return None
        return None

    def fetch_core_ac(self, anchors: List[str], tech_strings: List[str], limit: int = 30) -> List[Dict[str, Any]]:
        """Fetches open access articles from CORE.ac.uk."""
        anchor_group = ' OR '.join([f'"{t}"' for t in anchors])
        tech_group = ' OR '.join([f'"{t}"' for t in tech_strings])
        query = f"title:({anchor_group}) AND abstract:({tech_group})"
        params = {"q": query, "limit": limit}
        
        data = self._make_request(self.core_url, params=params, timeout=20)
        if not data:
            return []
            
        try:
            articles = []
            for i in data.get('results', []):
                # Safe navigation for CORE metadata
                journals = i.get('journals') or []
                first_journal = journals[0] if journals and journals[0] else {}
                venue_name = i.get('publisher') or first_journal.get('title') or "Unknown Venue"

                articles.append({
                    "Title": i.get('title', "Unknown Title"),
                    "Abstract": i.get('abstract', ""),
                    "Year": i.get('yearPublished', "N/A"), 
                    "URL": f"https://core.ac.uk/works/{i.get('id')}" if i.get('id') else "",
                    "Source": "CORE",
                    "Citations": 0,
                    "DOI": i.get('doi'),
                    "Type": i.get('type', "journal-article"),
                    "Venue": venue_name
                })
            return articles
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
        
        data = self._make_request(url, params=params, timeout=20)
        if not data:
            return []
            
        try:
            articles = []
            for i in data.get('results', []):
                raw_doi = i.get('doi') or ""
                doi_clean = raw_doi.replace('https://doi.org/', '').replace('http://doi.org/', '').lower()
                abstract_text = self._decode_openalex_abstract(i.get('abstract_inverted_index', {}))
                
                # Safe navigation for OpenAlex metadata
                primary_loc = i.get('primary_location') or {}
                source_info = primary_loc.get('source') or {}
                venue_name = source_info.get('display_name') or "Unknown Venue"
                
                articles.append({
                    "Title": i.get('display_name', "Unknown Title"),
                    "Abstract": abstract_text,
                    "Year": i.get('publication_year', "N/A"),
                    "URL": i.get('doi') or i.get('id') or "",
                    "Source": "OpenAlex",
                    "Citations": i.get('cited_by_count', 0),
                    "DOI": doi_clean,
                    "Type": i.get('type', "article"),
                    "Venue": venue_name
                })
            return articles
        except Exception as e:
            print(f"   [OpenAlex Error] {e}")
            return []

    def detect_peer_review(self, paper: Dict[str, Any]) -> str:
        """Heuristic to classify peer-review status based on source and type."""
        source = paper.get('Source')
        doc_type = str(paper.get('Type', '')).lower()
        
        if source == "Crossref":
            return "Yes"
        if source == "ArXiv":
            return "No (Preprint)"
        
        # Specific check for Semantic Scholar "Likely" status
        if source == "SemanticScholar" and "journalarticle" in doc_type.replace(" ", ""):
            return "Likely"
            
        if source in ["OpenAlex", "CORE", "SemanticScholar"]:
            # Check for journal articles or conference proceedings
            if any(t in doc_type for t in ["article", "proceedings", "journal"]):
                return "Yes"
        
        return "N/A"

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

        # Merge Venue and Peer_Reviewed
        if (existing.get('Venue') in [None, "", "Unknown Venue", "ArXiv"] or 
            (existing.get('Source') == "ArXiv" and new.get('Source') != "ArXiv")) and new.get('Venue'):
            existing['Venue'] = new['Venue']
        
        # Priority for Peer_Reviewed: Yes > Likely > No (Preprint) > N/A
        priority = {"Yes": 3, "Likely": 2, "No (Preprint)": 1, "N/A": 0}
        new_status = self.detect_peer_review(new)
        existing_status = existing.get('Peer_Reviewed', "N/A")
        
        if priority.get(new_status, 0) > priority.get(existing_status, 0):
            existing['Peer_Reviewed'] = new_status

    def _process_paper(self, paper: Dict, anchor_cat: str, tech_cat: str, anchor_list: List[str], tech_list: List[str]):
        """Deduplicates, scores, and merges a paper into the consolidated results (thread-safe)."""
        # 1. Track Identification
        source = paper.get('Source', 'Unknown')
        
        with self.lock:
            self.stats["identified"][source] = self.stats["identified"].get(source, 0) + 1
            
        title = paper.get('Title', '').strip()
        if not title: return
        
        # 2. Deduplication by Title-Slug (or DOI if available in future task)
        dedup_id = self.generate_slug(title)
        
        with self.lock:
            if dedup_id in self.seen_ids:
                self.stats["duplicates_removed"] += 1
                if dedup_id in self.consolidated_results:
                    self._merge_paper_metadata(self.consolidated_results[dedup_id], paper, anchor_cat, tech_cat)
                else:
                    # This means the first version was excluded. Check if THIS version qualifies.
                    full_text = f"{title} {paper.get('Abstract', '')}".lower()
                    matched_anchors = self.find_matching_terms(full_text, anchor_list)
                    
                    if matched_anchors:
                        new_score = self.calculate_score(title, paper.get('Abstract', ''))
                        if new_score >= self.settings.get('min_relevance_score', 0):
                            paper.update({
                                "Anchor_Category": anchor_cat,
                                "Matched_Anchors": matched_anchors,
                                "Tech_Category": tech_cat,
                                "Matched_Tech_Terms": self.find_matching_terms(full_text, tech_list),
                                "Relevance_Score": new_score,
                                "Peer_Reviewed": self.detect_peer_review(paper)
                            })
                            self.consolidated_results[dedup_id] = paper
                            self.stats["included_final"] += 1
                            self.stats["excluded_score"] -= 1 # Correct the stats
                return

            self.seen_ids.add(dedup_id)

            # 3. Anchor Filtering
            full_text = f"{title} {paper.get('Abstract', '')}".lower()
            matched_anchors = self.find_matching_terms(full_text, anchor_list)
            if not matched_anchors:
                self.stats["excluded_score"] += 1
                return

            # 4. Scoring and Exclusion
            paper.update({
                "Anchor_Category": anchor_cat,
                "Matched_Anchors": matched_anchors,
                "Tech_Category": tech_cat,
                "Matched_Tech_Terms": self.find_matching_terms(full_text, tech_list),
                "Relevance_Score": self.calculate_score(title, paper.get('Abstract', '')),
                "Peer_Reviewed": self.detect_peer_review(paper)
            })
            
            if paper["Relevance_Score"] >= self.settings.get('min_relevance_score', 0):
                self.consolidated_results[dedup_id] = paper
                self.stats["included_final"] += 1
            else:
                self.stats["excluded_score"] += 1

    def _api_worker(self, source_name: str, fetch_func, limit_per_source: int):
        """Worker thread function for a specific API source."""
        for anchor_cat, anchor_list in self.anchors.items():
            for tech_cat, tech_list in self.tech_strings.items():
                # print(f"   [{source_name}] Mining: {anchor_cat} x {tech_cat}")
                try:
                    results = fetch_func(anchor_list, tech_list, limit=limit_per_source)
                    for paper in results:
                        self._process_paper(paper, anchor_cat, tech_cat, anchor_list, tech_list)
                except Exception as e:
                    print(f"   [{source_name} Worker Error] {e}")
                
                if source_name == "CORE":
                    time.sleep(10) # Respect CORE's strict rate limit

    def run(self, limit_per_source: int = 100):
        print(f"🚀 Initializing Multi-Threaded Academic Hunter V2 Pipeline...")
        start_time = time.time()
        
        with self.lock:
            self.consolidated_results = {} 
            self.seen_ids = set() 
            self.stats = {
                "identified": {},
                "duplicates_removed": 0,
                "excluded_score": 0,
                "included_final": 0
            }

        workers = [
            ("ArXiv", self.fetch_arxiv),
            ("Crossref", self.fetch_crossref),
            ("Semantic Scholar", self.fetch_semantic_scholar),
            ("OpenAlex", self.fetch_openalex),
            ("CORE", self.fetch_core_ac)
        ]

        threads = []
        for name, func in workers:
            t = threading.Thread(target=self._api_worker, args=(name, func, limit_per_source))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        elapsed = time.time() - start_time
        print(f"\n⏱️  Mining completed in {elapsed:.2f} seconds.")
        
        with self.lock:
            results_list = list(self.consolidated_results.values())
        self.export_results(results_list)

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
                f.write(f"- **Venue:** {row.get('Venue', 'N/A')} | **Peer-Reviewed:** {row.get('Peer_Reviewed', 'N/A')}\n")
                f.write(f"- **Source:** {row['Source']} | **DOI:** {row.get('DOI', 'N/A')}\n")
                f.write(f"- **Anchors:** {row['Matched_Anchors']}\n")
                f.write(f"- [Link]({row['URL']})\n\n")
        
        # Generate PRISMA Flow Report
        self.generate_prisma_report(timestamp)

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

    def generate_prisma_report(self, timestamp: str):
        """Generates a PRISMA flow report in Markdown with a Mermaid diagram."""
        total_identified = sum(self.stats["identified"].values())
        duplicates = self.stats["duplicates_removed"]
        excluded = self.stats["excluded_score"]
        final = self.stats["included_final"]
        
        prisma_file = self.output_dir / f"FLUXO_PRISMA_{timestamp}.md"
        
        sources_mermaid = "\n".join([f"        S{i}[{source}: {count}]" for i, (source, count) in enumerate(self.stats["identified"].items())])
        sources_links = "\n".join([f"        S{i} --> A" for i in range(len(self.stats["identified"]))])

        mermaid_content = f"""```mermaid
graph TD
    subgraph Sources
{sources_mermaid}
    end
{sources_links}

    A[Records identified through database searching] --> B(Total Records Identified: {total_identified})
    B --> C{{Deduplication}}
    C -->|Duplicates Removed: {duplicates}| D[Records removed after deduplication]
    C --> E[Records for Screening: {total_identified - duplicates}]
    E --> F{{Relevance Scoring}}
    F -->|Excluded by Score/Anchors: {excluded}| G[Records excluded]
    F --> H[Final Records Included: {final}]
```"""

        with open(prisma_file, 'w', encoding='utf-8') as f:
            f.write(f"# PRISMA Flow Report - {timestamp}\n\n")
            f.write("## 1. Breakdown by Source\n")
            for source, count in self.stats["identified"].items():
                f.write(f"- **{source}:** {count}\n")
            f.write(f"\n- **Total Identified:** {total_identified}\n")
            f.write(f"- **Duplicates Removed:** {duplicates}\n")
            f.write(f"- **Excluded by Score/Anchors:** {excluded}\n")
            f.write(f"- **Final Included:** {final}\n\n")
            f.write("## 2. Visual Flow (Mermaid)\n\n")
            f.write(mermaid_content)

        print(f"📊 PRISMA Report: {prisma_file}")

if __name__ == "__main__":
    hunter = AcademicHunter()
    hunter.run(limit_per_source=100)
