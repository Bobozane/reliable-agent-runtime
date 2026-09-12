"""Minimal real stdio server used by the official MCP adapter test."""

from mcp.server.mcpserver import MCPServer


server = MCPServer("runtime-stdio-fixture")


@server.tool(
    name="echo",
    description="Return the query for integration testing",
    structured_output=True,
)
def echo(query: str) -> dict[str, str]:
    return {"query": query, "source": "stdio-fixture"}


if __name__ == "__main__":
    server.run(transport="stdio")
