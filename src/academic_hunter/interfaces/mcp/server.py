from mcp.server.fastmcp import FastMCP
from .tools.configuration import read_config, update_config, list_config_history, restore_config_by_id
from .tools.search import run_search, read_latest_report
from .tools.discovery import fetch_paper_by_doi, explore_citation_graph, fetch_multiple_abstracts, quick_topic_discovery
from .tools.obsidian import export_to_obsidian
from .tools.rag import semantic_search, index_papers, vector_store_stats, ask_papers

def create_mcp_server() -> FastMCP:
    """
    Instantiate the FastMCP server and register the tools available to the LLMs.
    """
    mcp = FastMCP("academic-hunter", dependencies=["requests", "pandas", "bibtexparser", "chromadb"])

    # Register tools
    mcp.tool()(run_search)
    mcp.tool()(read_latest_report)
    mcp.tool()(read_config)
    mcp.tool()(update_config)
    mcp.tool()(list_config_history)
    mcp.tool()(restore_config_by_id)
    mcp.tool()(fetch_paper_by_doi)
    mcp.tool()(explore_citation_graph)
    mcp.tool()(fetch_multiple_abstracts)
    mcp.tool()(quick_topic_discovery)
    mcp.tool()(export_to_obsidian)

    # RAG tools
    mcp.tool()(semantic_search)
    mcp.tool()(index_papers)
    mcp.tool()(vector_store_stats)
    mcp.tool()(ask_papers)

    return mcp

def run_mcp_server():
    """
    Executa o servidor MCP (geralmente via Stdio).
    """
    server = create_mcp_server()
    server.run()

if __name__ == "__main__":
    run_mcp_server()
