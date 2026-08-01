# Design Spec: Task 3 - Peer-Review & Venue Detection

## Goal
Implement automated classification for peer-review status and extraction of publication venues (journals/conferences) across all integrated scholarly APIs.

## Architecture & Data Flow

### 1. Enhanced Metadata Fetching
Each fetcher in `AcademicHunter` will be updated to extract two new fields from their respective API responses:
- `Type`: The raw document type (e.g., "journal-article", "preprint").
- `Venue`: The name of the publication venue (e.g., "Nature", "ICLR 2024").

#### API Mapping Table
| Source | Type Field | Venue Field |
| :--- | :--- | :--- |
| **ArXiv** | Fixed: "preprint" | Fixed: "ArXiv" |
| **Crossref** | `type` | `container-title[0]` |
| **Semantic Scholar** | `publicationTypes` (list) | `journal.name` or `venue` |
| **CORE** | `type` | `publisher` or `journals[0].title` |
| **OpenAlex** | `type` | `primary_location.source.display_name` |

### 2. Peer-Review Detection Logic
A new method `detect_peer_review(self, paper: Dict[str, Any]) -> str` will implement the following heuristic:
- **"Yes"**: If `Source` is "Crossref" OR (`Source` in ["OpenAlex", "CORE"] AND `Type` is `article` or contains `proceedings`).
- **"No (Preprint)"**: If `Source` is "ArXiv".
- **"Likely"**: If `Source` is "SemanticScholar" AND `Type` contains "JournalArticle".
- **"N/A"**: Default fallback.

### 3. Integration & Consolidation
- **`run()`**: Will call `detect_peer_review` for each paper and store the result in a new field `Peer_Reviewed`.
- **`_merge_paper_metadata()`**: Will be updated to prioritize more descriptive `Venue` and more certain `Peer_Reviewed` status (e.g., "Yes" > "Likely" > "N/A").

### 4. Export
- **CSV**: Add `Peer_Reviewed` and `Venue` columns.
- **Markdown**: Include `Venue` and `Peer_Reviewed` in the paper summary.

## Testing Strategy
- **Unit Test**: Add `test_peer_review_detection` in `tests/test_rigor.py` to verify the heuristic against mock paper objects from different sources.
- **Integration Test**: Verify that the exported CSV contains the new columns.

## Error Handling
- Use `.get()` and default values to prevent crashes on missing API fields.
- Fallback to "N/A" or "Unknown" for missing venues.
