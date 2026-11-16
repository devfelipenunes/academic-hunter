# Architecture of Academic Hunter

Academic Hunter is designed using **Hexagonal Architecture** (also known as Ports and Adapters). This ensures that the core domain logic (the scientific research engine) is strictly isolated from delivery mechanisms like the MCP Server.

## High-Level System Diagram

```mermaid
graph TD
    %% Define styles
    classDef core fill:#2d3436,stroke:#74b9ff,stroke-width:2px,color:white
    classDef interface fill:#0984e3,stroke:#74b9ff,stroke-width:2px,color:white
    classDef plugin fill:#00b894,stroke:#55efc4,stroke-width:2px,color:white
    classDef external fill:#d63031,stroke:#ff7675,stroke-width:2px,color:white

    subgraph External["External World"]
        MCP_Client["MCP Client (Claude/Cursor)"]:::external
        APIs["Scientific APIs (Semantic Scholar, arXiv)"]:::external
    end

    subgraph Interfaces["Interfaces (Delivery Layer)"]
        MCP_Server["FastMCP Server"]:::interface
        DB["SQLite DB (.academic_hunter)"]:::interface
    end

    subgraph App["App (Composition Root)"]
        App["app/main.py (AcademicHunter)"]:::interface
    end

    subgraph Core["Core Engine (Domain Layer)"]
        Pipeline["pipeline/manager.py"]:::core
        Steps["pipeline/steps.py"]:::core
        Models["models/schema.py"]:::core
        Screening["screening/"]:::core
    end

    subgraph Plugins["Plugins (Infrastructure Layer)"]
        Connectors["API Connectors"]:::plugin
        Exporters["CSV & Markdown Exporters"]:::plugin
        Screeners["Screeners (NLP/Keyword)"]:::plugin
        VectorStores["Vector Stores (ChromaDB)"]:::plugin
    end

    %% Relationships
    MCP_Client --> MCP_Server

    App --> Pipeline
    MCP_Server --> App
    MCP_Server <--> DB

    Pipeline --> Steps
    Pipeline --> Screening
    Pipeline --> Models

    Steps --> Connectors
    Connectors --> APIs

    Pipeline --> Exporters
```

## Directory Structure Explained

1. **`src/academic_hunter/core/`**: The brain of the project. Contains the business logic for deduplication, relevance scoring, and the search pipeline. It has zero knowledge of MCP.
2. **`src/academic_hunter/plugins/`**: Adapters for external services.
    - `connectors/` (APIs like Semantic Scholar)
    - `exporters/` (Markdown/CSV)
    - `screeners/` (NLP Semantic Evaluators)
    - `vector_stores/` (RAG / ChromaDB Storage)
3. **`src/academic_hunter/app/`**: The composition root. `main.py` holds `AcademicHunter`, the facade that wires a configuration to the pipeline and the plugins; nothing here decides anything the core does not.
4. **`src/academic_hunter/interfaces/`**: The entry points.
    - `interfaces/mcp/` exposes the Core as an MCP Server using FastMCP.
    - (Future) `interfaces/cli/` or `interfaces/api/` can be added here.
