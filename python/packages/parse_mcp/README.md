# parse-mcp

Official Python client and agent-framework wrappers for the PARSE MCP surface.

## What it does
- discovers the active PARSE MCP tool schema from a running PARSE server
- executes MCP-visible PARSE tools through the HTTP bridge
- builds ready-to-use wrappers for:
  - LangChain
  - LlamaIndex
  - CrewAI

## Runtime requirements
A running PARSE server on `http://127.0.0.1:8766` (or another configured base URL) with Task 5's external API endpoints enabled:
- `GET /openapi.json`
- `GET /api/mcp/exposure`
- `GET /api/mcp/tools`
- `GET /api/mcp/tools/{toolName}`
- `POST /api/mcp/tools/{toolName}`

## Install

```bash
pip install parse-mcp
pip install 'parse-mcp[langchain]'
pip install 'parse-mcp[llamaindex]'
pip install 'parse-mcp[crewai]'
pip install 'parse-mcp[all]'
```

## Basic usage

```python
from parse_mcp import ParseMcpClient

client = ParseMcpClient(base_url="http://127.0.0.1:8766")
for tool in client.list_tools():
    print(tool.name, tool.family)

result = client.call_tool("project_context_read", {"include": ["project", "source_index"]})
print(result)
```

## LangChain

```python
from parse_mcp import ParseMcpClient, build_langchain_tools

client = ParseMcpClient()
tools = build_langchain_tools(client)
```

## LlamaIndex

```python
from parse_mcp import ParseMcpClient, build_llamaindex_tools

client = ParseMcpClient()
tools = build_llamaindex_tools(client)
```

## CrewAI

```python
from parse_mcp import ParseMcpClient, build_crewai_tools

client = ParseMcpClient()
tools = build_crewai_tools(client)
```
