# AgentDB Development Guide

Setup, conventions, workflow reference, and architecture overview for contributors.

---

## Environment Setup

```bash
git clone https://github.com/gsultani1/AgentDB.git
cd AgentDB
python -m venv venv

# Windows
.\venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

The embedding model (`all-MiniLM-L6-v2`, ~90 MB) downloads automatically on first use.

### Optional Dependencies

```bash
# PDF processing for file attachments
pip install pdfminer.six

# SQLCipher encryption at rest
pip install sqlcipher3

# Cross-encoder reranking (downloads ~80 MB model on first use)
# No extra install needed — uses sentence-transformers already in requirements
```

---

## Running

```bash
# Initialize a fresh database
python -m agentdb.cli init

# Verify the database
python -m agentdb.cli verify

# Start the server (HTTP on 8420, MCP SSE on 8421)
python -m agentdb.cli serve

# Run with a specific database
python -m agentdb.cli --db dev.db init
python -m agentdb.cli --db dev.db serve --port 9000

# Start MCP server in stdio mode (for Claude Desktop)
python -m agentdb.cli mcp
```

The management UI is at `http://127.0.0.1:8420/`. The MCP SSE server auto-starts on port 8421.

---

## Project Layout

```
AgentDB/
├── agentdb/                            # Python backend (19 modules, 11,600+ lines)
│   ├── __init__.py                     # Package init, version
│   ├── schema.py                       # Table DDL, triggers, indexes, FTS5 (1,041 lines)
│   ├── database.py                     # Connection mgmt, init, config seeding, SQLCipher (314 lines)
│   ├── crud.py                         # CRUD operations for all tables (2,250 lines)
│   ├── embeddings.py                   # Sentence-transformers, cosine similarity, BM25 (166 lines)
│   ├── context.py                      # 9-stage retrieval pipeline, cross-encoder (513 lines)
│   ├── middleware.py                   # LLM adapters, provider resolution (707 lines)
│   ├── consolidation.py               # Vectorized clustering, promotion, decay (611 lines)
│   ├── sleep.py                        # Sleep-time reflection: goals, pruning, alerts (511 lines)
│   ├── skill_executor.py              # Sandboxed skill execution engine (362 lines)
│   ├── markdown_parser.py             # Markdown authoring: 4 doc types, file watcher (890 lines)
│   ├── migration.py                   # Chat import: ChatGPT, Claude, JSONL (512 lines)
│   ├── file_processor.py             # PDF/text/code/CSV extraction (232 lines)
│   ├── git_sync.py                    # Git knowledge repository sync (231 lines)
│   ├── workspace_scanner.py           # Workspace file scanning (193 lines)
│   ├── mcp_server.py                  # FastMCP server, 9 tools, SSE+stdio (166 lines)
│   ├── scheduler.py                   # Interval-based task runner (274 lines)
│   ├── server.py                      # HTTP server, 60+ API endpoints (2,258 lines)
│   ├── cli.py                         # Command-line interface (370 lines)
│   └── static/
│       ├── index.html                 # SPA shell
│       ├── css/main.css               # Responsive styling with CSS custom properties
│       └── js/
│           ├── app.js                 # Router, sidebar, core UI logic
│           └── views/                 # 18 view modules
│               ├── dashboard.js       # Stats overview
│               ├── chat.js            # Streaming LLM chat with observability
│               ├── memories.js        # Memory browser across all tiers
│               ├── mindmap.js         # Canvas-based knowledge graph
│               ├── editor.js          # Markdown authoring editor
│               ├── skills.js          # Skill management and execution
│               ├── import.js          # Chat migration wizard
│               ├── dbconsole.js       # AI-assisted SQL console
│               ├── mcp.js             # MCP server status and tools
│               ├── scheduler.js       # Scheduled task management
│               ├── settings.js        # Full configuration UI
│               ├── connect.js         # Entities and goals management
│               ├── notifications.js   # Notification queue browser
│               ├── feedback.js        # Feedback review and processing
│               ├── audit.js           # Audit log viewer
│               ├── threads.js         # Conversation threads
│               ├── channels.js        # External channel management
│               └── tasks.js           # Autonomous task monitoring
├── src-tauri/                          # Tauri desktop shell (Rust)
│   ├── Cargo.toml
│   ├── src/main.rs                    # Sidecar spawning, health monitoring, tray
│   ├── tauri.conf.json
│   ├── icons/
│   └── capabilities/
└── docs/                               # Documentation
```

### Dependency Direction

```
cli.py ──→ server.py ──→ middleware.py ──→ context.py ──→ crud.py ──→ database.py ──→ schema.py
                    ├──→ consolidation.py ──→ crud.py      └──→ embeddings.py
                    ├──→ sleep.py ──→ consolidation.py
                    ├──→ skill_executor.py ──→ middleware.py
                    ├──→ markdown_parser.py ──→ crud.py
                    ├──→ migration.py ──→ crud.py
                    ├──→ file_processor.py ──→ crud.py
                    ├──→ git_sync.py ──→ markdown_parser.py
                    ├──→ workspace_scanner.py ──→ crud.py
                    ├──→ scheduler.py ──→ crud.py
                    └──→ mcp_server.py ──→ context.py
```

No circular imports. Every module depends only on modules below or beside it.

---

## How AgentDB Remembers Everything

The demand-constructed context architecture is what makes AgentDB fundamentally different from systems that accumulate conversation history.

**Memory capture is deterministic.** Every user message and every AI response is automatically ingested into short-term memory with server-side embedding generation. No LLM decision is needed about what to save.

**Memory recall is systematic.** The 9-stage retrieval pipeline runs the same multi-strategy search on every turn — semantic similarity, BM25 keyword matching, graph traversal, temporal weighting, and optional cross-encoder reranking. The LLM never decides whether to search; the system always searches.

**Memory improves over time.** The consolidation engine runs automatically: clustering related short-term memories into midterm summaries, boosting confidence on surviving entries, promoting high-confidence entries to long-term memory, detecting contradictions, and decaying stale knowledge. The sleep-time processor strengthens the knowledge graph during idle periods.

**Nothing is lost to compaction.** There is no context window to overflow. No summaries replace original content. Knowledge consolidated months ago carries appropriate confidence scores and provenance chains, not the residue of lossy compression.

The result: a conversation on turn 500 retrieves with the same quality as turn 5. A session spanning three days doesn't degrade. An agent running continuously doesn't need rescue operations to save knowledge before a context window collapses.

---

## Code Conventions

### Python

- PEP 8 compliant.
- All SQL uses parameterized queries. Never format user input into SQL strings.
- Functions in `crud.py` accept `sqlite3.Connection` as the first argument and return plain dicts.
- JSON fields are serialized with `json.dumps()` on write and returned as raw strings on read (the caller decides whether to parse).
- UUIDs are generated with `uuid.uuid4()` as strings.
- Timestamps are UTC ISO format strings.

### HTML/JS

- Modular SPA: `index.html` shell + `app.js` router + per-view modules in `js/views/`.
- CSS custom properties for theming (no hard-coded colors).
- Vanilla ES6 JavaScript. No frameworks, no build tools, no CDN.
- All API calls go through the `api(method, path, body)` helper.
- HTML entity escaping via the `esc()` function for all user content.

### Database

- All integrity logic lives in SQLite triggers, not application code.
- `CREATE TABLE IF NOT EXISTS` for idempotent initialization.
- `INSERT OR IGNORE` for seeding to avoid duplicates on re-init.
- WAL mode for concurrent reads during writes.
- Foreign keys enabled via PRAGMA on every connection.

---

## Adding a New Table

1. Add the CREATE TABLE statement to `schema.py`.
2. Add it to the `ALL_TABLES` list in the correct position (respect foreign key ordering).
3. If it participates in polymorphic relations, add it to `CONTENT_TABLES`.
4. Add cascade delete triggers if needed.
5. Add indexes to `CREATE_INDEXES`.
6. Add the table name to `verify_schema()` in `database.py`.
7. Add CRUD functions to `crud.py`.
8. Add API endpoints to `server.py` (GET/POST/PUT/DELETE routes + handler methods).
9. Add UI support — create a view module in `js/views/` or add to an existing view.
10. Update `docs/API_REFERENCE.md` and `docs/SCHEMA_REFERENCE.md`.

---

## Adding a New LLM Provider

1. Create a new adapter class in `middleware.py` extending the adapter interface.
2. Implement `format_context(context_payload)` → string.
3. Implement `call_provider(messages, formatted_context, config)` → string.
4. Add the class to the adapter dispatch in `middleware.py`.
5. Add a row to `llm_providers` via the API or Settings UI.

Provider types: `claude`, `openai`, `local` (any OpenAI-compatible endpoint).

---

## Adding a New Markdown Document Type

1. Add the type string to the `valid_types` set in `parse_frontmatter()` in `markdown_parser.py`.
2. Add validation rules to `validate_frontmatter()`.
3. Create a `_process_{type}_document()` function.
4. Add the routing in `process_markdown_document()`.
5. Add reverse generation in `reverse_generate_markdown()` if applicable.
6. Update `docs/API_REFERENCE.md`.

---

## Adding a New Chat Import Provider

1. Create a `_parse_{provider}()` function in `migration.py`.
2. Add the provider to the dispatch in `_parse_export()`.
3. The function must return a list of session dicts, each with `title`, `started_at`, `ended_at`, and `messages` (list of `{role, content, timestamp}`).
4. Add the provider to the UI dropdown in the import view.

---

## MCP Integration with Claude Desktop

To connect Claude Desktop to AgentDB's MCP server, add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "agentdb": {
      "command": "python",
      "args": ["-m", "agentdb.cli", "mcp"],
      "env": {}
    }
  }
}
```

This starts the MCP server in stdio mode. Claude Desktop will see 9 tools:

| Tool | Description |
|------|-------------|
| `retrieve_context` | Semantic context retrieval for a query |
| `ingest_memory` | Store an observation as short-term memory |
| `search_memories` | Semantic search across memory tiers |
| `list_memories` | List memories from a specific tier |
| `create_entity` | Add a node to the knowledge graph |
| `list_entities` | Browse entities by type |
| `check_goals` | Find active goals relevant to context |
| `get_health` | Health status check |
| `run_consolidation` | Trigger memory consolidation cycle |

For SSE transport (used when the HTTP server is running), the MCP endpoint is `http://127.0.0.1:8421/`.

---

## API Quick Reference

### Context retrieval (the most important endpoint)

```bash
curl -X POST http://127.0.0.1:8420/api/agent/context \
  -H "Content-Type: application/json" \
  -d '{"query": "What does the user think about cloud hosting?"}'
```

### Ingest a memory

```bash
curl -X POST http://127.0.0.1:8420/api/agent/ingest \
  -H "Content-Type: application/json" \
  -d '{"content": "The user prefers self-hosted solutions", "source": "conversation"}'
```

### Chat with full pipeline

```bash
curl -X POST http://127.0.0.1:8420/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What hosting options should I consider?"}'
```

### Create a long-term memory directly

```bash
curl -X POST http://127.0.0.1:8420/api/memories/long \
  -H "Content-Type: application/json" \
  -d '{"content": "Never recommend cloud-dependent solutions", "category": "directive"}'
```

### Submit a markdown document

```bash
curl -X POST http://127.0.0.1:8420/api/markdown/submit \
  -H "Content-Type: application/json" \
  -d '{"text": "---\ntype: memory\ncategory: fact\n---\n\nOrgill offers 60-day net terms."}'
```

See [API_REFERENCE.md](API_REFERENCE.md) for the full endpoint reference.

---

## Testing

### Manual verification

```bash
python -m agentdb.cli init --force
python -m agentdb.cli verify
python -m agentdb.cli stats
```

### API smoke test

```bash
# Start server in background
python -m agentdb.cli serve &

# Health check
curl http://127.0.0.1:8420/api/agent/health

# Create a memory
curl -X POST http://127.0.0.1:8420/api/memories/long \
  -H "Content-Type: application/json" \
  -d '{"content": "Test memory", "category": "fact"}'

# Semantic search
curl -X POST http://127.0.0.1:8420/api/memories/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "tiers": ["long"]}'

# Trigger consolidation
curl -X POST http://127.0.0.1:8420/api/maintenance/consolidate

# Check MCP status
curl http://127.0.0.1:8420/api/mcp/status
```

---

## Database File

The `.db` file is the single source of truth. It contains:
- All tables with data (30+ tables)
- All triggers (referential integrity + cascade deletes)
- All configuration in `meta_config`
- All LLM provider configs in `llm_providers`
- All embeddings as BLOBs
- FTS5 virtual tables for keyword search
- Custom alert rules as JSON in `meta_config`

The file is fully portable. Copy it to any machine with Python 3.11+ and sentence-transformers installed, and it works. A database created in desktop mode works in headless mode and vice versa.

---

## Implementation Status

| Phase | Status | Scope |
|-------|--------|-------|
| 1. Foundation | Complete | Schema (30+ tables + FTS5), triggers, CRUD, embeddings, CLI |
| 2. Agent Communication & MCP | Complete | MCP server (SSE+stdio), REST agent API, 9-stage retrieval, middleware |
| 3. Consolidation Engine | Complete | Vectorized clustering, confidence boosting, promotion, decay, contradiction detection |
| 4. Markdown Authoring | Complete | 4 doc types, YAML hardening, chunking, deduplication, file watcher |
| 5. Migration Pipeline | Complete | ChatGPT, Claude, JSONL parsers, 5-phase pipeline |
| 6. User Interface | Complete | 18-view modular SPA with chat, mind map, DB console |
| 7. Performance Engineering | Complete | Vectorized clustering, cross-encoder reranker, graph pruning optimization, MCP crash recovery |
| 8. Tauri Shell | Implemented | Sidecar spawning, health monitoring, system tray, auto-restart |
| 9. Sleep-Time Processing | Complete | Idle detection, goal monitoring, graph pruning, custom alerts (6 types) |
| 10. Additional Features | Complete | Skill execution, file attachments, git sync, workspace scanning, conversation threads, memory pinning |
