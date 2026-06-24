# The Core Engine (Academic Hunter)

The `core/` directory is the heart of Academic Hunter. It is designed using Domain-Driven Design (DDD) principles and is completely agnostic to external delivery interfaces like the MCP server or the CLI.

If you are a Data Engineer or Python Developer looking to improve the systematic review algorithms, this is where you will spend most of your time.

## Directory Breakdown

### 1. `pipeline/` (The Data Orchestrator)
The pipeline is responsible for the lifecycle of a scientific paper within our system.
- **`manager.py`**: Orchestrates the flow. It takes the user's `config.json` anchors, asks the plugins to fetch data, and then passes the raw data to the enrichment and screening layers.
- **`enricher.py`**: Merges metadata. If Semantic Scholar returns a paper without an abstract, the enricher will query CrossRef using the DOI to fill in the missing gaps.
- *(Future Evolution)*: This layer will house the Heuristic Deduplication Engine (Levenshtein distance matching).

### 2. `nlp/` (Natural Language Processing & Screening)
This module acts as the "Peer Reviewer".
- **`screening.py`**: Once a paper is fetched, the NLP layer reads the abstract and title. It calculates a **Technical Elite Score** based on the weights defined in your `config.json`. Papers that don't meet a minimum threshold are discarded.
- *(Future Evolution)*: Transitioning from regex/keyword matching to Local Semantic Embeddings (using ONNX and Sentence Transformers).

### 3. `engine/` (Execution)
- **`search.py`**: Manages the grid-search logic. It combines `anchors` (e.g., "CBDC") with `technical_strings` (e.g., "Zero Knowledge Proof") to generate highly specific queries for the API Connectors.
- *(Future Evolution)*: Full `asyncio` implementation to handle 50,000+ abstracts concurrently.

### 4. `models/` (Data Schemas)
- Contains Pydantic models (like the `Paper` schema) that ensure type safety across the entire application. Every plugin must return data that strictly conforms to these models.

### 5. `infra/` (Infrastructure)
- **`config.py`**: Handles the loading and fallback resolution of `config.json`.
- Logging setup and other system-level utilities.

## How the Core interacts with Plugins
The Core does not know *how* to talk to Semantic Scholar. It relies on `plugins/connectors/`. The Core simply says: *"Fetch me papers matching X"*, and the plugins handle the HTTP requests, rate-limits, and mapping the JSON responses into the standard `Paper` model.
