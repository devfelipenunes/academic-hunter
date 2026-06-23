from mcp.server.fastmcp import FastMCP
from .config_tools import read_config, update_config
from .search_tools import run_search, read_latest_report
from .discovery_tools import fetch_paper_by_doi, explore_citation_graph, fetch_multiple_abstracts, quick_topic_discovery

def create_mcp_server() -> FastMCP:
    """
    Instancia o servidor FastMCP e registra as ferramentas disponíveis para os LLMs.
    """
    mcp = FastMCP("Academic Hunter MCP")
    
    # Registrando as ferramentas
    mcp.tool()(run_search)
    mcp.tool()(read_latest_report)
    mcp.tool()(read_config)
    mcp.tool()(update_config)
    mcp.tool()(fetch_paper_by_doi)
    mcp.tool()(explore_citation_graph)
    mcp.tool()(fetch_multiple_abstracts)
    mcp.tool()(quick_topic_discovery)
    
    return mcp

def run_mcp_server():
    """
    Executa o servidor MCP (geralmente via Stdio).
    """
    server = create_mcp_server()
    server.run()

if __name__ == "__main__":
    run_mcp_server()
