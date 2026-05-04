# MCP (Model Context Protocol) Integration

swadb ships an MCP server that exposes 9 tools to any MCP-aware client
(Claude Desktop, Cursor, Continue.dev, etc.). The server runs on port
**8421** by default, alongside the main HTTP server on 8420.

## Tools exposed

| Tool | Purpose |
|---|---|
| `retrieve_context` | Run the full retrieval pipeline for a query (memories, entities, goals, skills) |
| `ingest_memory` | Store a new short-term memory |
| `search_memories` | Semantic search across one tier |
| `list_memories` | List memories by tier with limit |
| `create_entity` | Create a knowledge-graph entity |
| `list_entities` | List entities, optionally filtered by type |
| `check_goals` | Check active goals against context |
| `get_health` | Server health probe |
| `run_consolidation` | Trigger a consolidation cycle |

Each tool's input schema is published via the MCP protocol and is
auto-discoverable by clients.

## Transport options

| Transport | When to use |
|---|---|
| **stdio** | Most desktop clients (Claude Desktop, Cursor). The MCP client launches `swadb mcp` as a subprocess and talks over stdin/stdout. |
| **SSE** | Network-accessible clients, multi-tenant setups, or running swadb on a different machine. `swadb serve` auto-starts the SSE server. |

## Client configuration examples

### Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "swadb": {
      "command": "swadb",
      "args": ["mcp", "--transport", "stdio"],
      "env": {}
    }
  }
}
```

Restart Claude Desktop. The `swadb` tools should appear in the tools
menu.

### Cursor

`~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "swadb": {
      "command": "swadb",
      "args": ["mcp", "--transport", "stdio"]
    }
  }
}
```

### SSE-based client

If your client supports SSE-based MCP servers, point it at:

```
http://127.0.0.1:8421/sse
```

This is auto-started by `swadb serve` (controlled by `mcp_enabled` in
`meta_config`).

## Per-client database paths

If you want different MCP clients to use different databases (e.g.
"work" vs "personal"), point each at its own DB:

```json
{
  "mcpServers": {
    "swadb-work": {
      "command": "swadb",
      "args": ["--db", "/path/to/work.db", "mcp", "--transport", "stdio"]
    },
    "swadb-personal": {
      "command": "swadb",
      "args": ["--db", "/path/to/personal.db", "mcp", "--transport", "stdio"]
    }
  }
}
```

Each `swadb mcp` invocation opens its own connection. They can run
concurrently because SQLite WAL mode supports multiple readers.

## Authentication

MCP connections from local clients (stdio transport) inherit OS-level
trust — there's no key auth. SSE connections honor the same
`agent_api_key` config that the HTTP `/api/agent/*` surface uses; if
set, the SSE endpoint requires it as a header or query param.

## Tool calling conventions

All tools follow the swadb response envelope:

```json
{
  "status": "ok" | "error",
  "data": <result>,
  "error": <message_if_error>
}
```

Specific tool inputs are documented at runtime via MCP introspection.
The `retrieve_context` tool is the most-used; its core inputs are:

```json
{
  "query": "what does the user prefer?",
  "agent_id": "default",
  "filters": {"tier": ["short", "mid", "long"]}
}
```

## Crash recovery

The MCP server (when run via `swadb serve`) runs in a supervised
thread that auto-restarts on crash, with backoff: up to 5 failures
within a 60-second window before the supervisor gives up. This is
visible in the Settings → MCP view.

## Performance notes

- The first `retrieve_context` call after server start triggers a
  ~2-second embedding-model warmup. Subsequent calls are fast.
- Repeated identical queries hit the **query cache** (warmed during
  sleep cycles) and return in O(1) — typically <5ms.
- For workspaces with >10k memories, install `swadb[ann]` so the HNSW
  index handles the semantic-search stage in sub-millisecond time.
