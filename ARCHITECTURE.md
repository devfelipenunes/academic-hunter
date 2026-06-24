# Architecture of Academic Hunter

Academic Hunter is designed using **Hexagonal Architecture** (also known as Ports and Adapters). This ensures that the core domain logic (the scientific research engine) is strictly isolated from delivery mechanisms like the CLI or the MCP Server.

## High-Level System Diagram

```mermaid
graph TD
    %% Define styles
    classDef core fill:#2d3436,stroke:#74b9ff,stroke-width:2px,color:white
    classDef interface fill:#0984e3,stroke:#74b9ff,stroke-width:2px,color:white
    classDef plugin fill:#00b894,stroke:#55efc4,stroke-width:2px,color:white
    classDef external fill:#d63031,stroke:#ff7675,stroke-width:2px,color:white

    subgraph External["External World"]
        CLI["Command Line (User)"]:::external
        MCP_Client["MCP Client (Claude/Cursor)"]:::external
        APIs["Scientific APIs (Semantic Scholar, arXiv)"]:::external
    end

    subgraph Interfaces["Interfaces (Delivery Layer)"]
        CLI_Adapter["main.py (CLI Adapter)"]:::interface
        MCP_Server["FastMCP Server"]:::interface
        DB["SQLite DB (.academic_hunter)"]:::interface
    end

    subgraph Core["Core Engine (Domain Layer)"]
        Pipeline["pipeline/manager.py"]:::core
        Engine["engine/search.py"]:::core
        Models["models/schemas.py"]:::core
        NLP["nlp/screening.py"]:::core
    end

    subgraph Plugins["Plugins (Infrastructure Layer)"]
        Connectors["API Connectors"]:::plugin
        Exporters["CSV & Markdown Exporters"]:::plugin
        Screeners["Screeners (NLP/Keyword)"]:::plugin
        VectorStores["Vector Stores (ChromaDB)"]:::plugin
    end

    %% Relationships
    CLI --> CLI_Adapter
    MCP_Client --> MCP_Server

    CLI_Adapter --> Pipeline
    MCP_Server --> Pipeline
    MCP_Server <--> DB

    Pipeline --> Engine
    Pipeline --> NLP
    Pipeline --> Models

    Engine --> Connectors
    Connectors --> APIs

    Pipeline --> Exporters
```

## Directory Structure Explained

1. **`src/academic_hunter/core/`**: The brain of the project. Contains the business logic for deduplication, relevance scoring, and the search pipeline. It has zero knowledge of MCP or CLI.
2. **`src/academic_hunter/plugins/`**: Adapters for external services.
    - `connectors/` (APIs like Semantic Scholar)
    - `exporters/` (Markdown/CSV)
    - `screeners/` (NLP Semantic Evaluators)
    - `vector_stores/` (RAG / ChromaDB Storage)
3. **`src/academic_hunter/interfaces/`**: The entry points. 
    - `interfaces/mcp/` exposes the Core as an MCP Server using FastMCP. 
    - (Future) `interfaces/cli/` or `interfaces/api/` can be added here.
4. **`docs/superpowers/agents/`**: Contains the Multi-Agent prompts (`01_orchestrator.md`, `02_hunter.md`, `03_synthesizer.md`) meant to be used by LLMs connecting via MCP.
