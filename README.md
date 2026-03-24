# AgentDB

A sovereign, local-first agent memory system with tiered knowledge, an empirical knowledge graph, MCP-native agent communication, multi-agent support, markdown authoring, and external chat migration.

**MIT License — Sultani Investments, LLC**

---

## What It Does

AgentDB gives AI agents persistent, structured memory. It stores what the agent learns across conversations, organizes it into short-term, midterm, and long-term tiers, and retrieves the most relevant context when the agent needs it. The entire system lives in a single portable SQLite file.

The defining architectural principle is **demand-constructed context**. AgentDB doesn't accumulate conversation history in a growing context window and compress it when the window fills (the accumulate-and-compact model). Instead, every turn constructs a fresh, purpose-built context payload by querying the database for memories, entities, goals, and skills relevant to the current query. Nothing accumulates. Nothing gets compressed. The LLM sees exactly what the retrieval pipeline determines is relevant — scored and ranked across all three tiers, weighted by confidence, recency, and graph proximity. A conversation that runs for six hours gets the same retrieval quality on message 500 as it did on message 5.

### Core Capabilities

- **Tiered memory** with automatic promotion, decay, and consolidation
- **Knowledge graph** connecting memories, entities, skills, and goals through typed relations
- **Multi-agent support** with scoped memory access per agent
- **Semantic search** using locally-generated embeddings (no external API calls)
- **Multi-strategy retrieval** combining vector similarity, BM25 keyword search, graph traversal, and temporal weighting
- **MCP server** exposing memory tools via stdio and SSE transports
- **Chat interface** with streaming LLM responses and context-aware conversations
- **Markdown authoring** for direct knowledge injection via files or a built-in editor
- **Chat migration** from ChatGPT, Claude, and generic JSONL exports
- **Provider-agnostic LLM middleware** with adapters for Claude, OpenAI, and local LLMs
- **DB console** with AI-assisted SQL query generation
- **Sleep-time reflection** for idle-period consolidation, goal monitoring, and graph pruning
- **Scheduled tasks** with interval-based execution
- **Workspace scanning** for local file environment awareness
- **Mind map visualization** of the knowledge graph
- **Full audit trail** of every operation on every table
- **Single-file portability** — copy the `.db` file to any machine and it works

---

## Quick Start

### Prerequisites

- Python 3.11+
- Git

### Setup

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

### Initialize the Database

```bash
python -m agentdb.cli init
```

This creates `agentdb.db` in the current directory with all tables, triggers, indexes, FTS5 virtual tables, default configuration values, and a default agent.

### Verify

```bash
python -m agentdb.cli verify
python -m agentdb.cli stats
python -m agentdb.cli config list
```

### Start the Server

```bash
python -m agentdb.cli serve
```

The server starts on `http://127.0.0.1:8420`. Open that URL in a browser for the management UI.

- **Management UI**: `http://127.0.0.1:8420/`
- **Operator API**: `http://127.0.0.1:8420/api/`
- **Agent API**: `http://127.0.0.1:8420/api/agent/`
- **MCP Server (SSE)**: `http://127.0.0.1:8421/` (auto-started with the UI)

### Use a Custom Database Path

```bash
python -m agentdb.cli --db /path/to/my.db init
python -m agentdb.cli --db /path/to/my.db serve --port 9000
```

---

## Project Structure

```
AgentDB/
├── README.md
├── requirements.txt                    # Python deps: sentence-transformers, numpy, mcp
├── package.json                        # Tauri CLI config
├── agentdb/                            # Python backend (8,400+ lines)
│   ├── __init__.py                     # Package init, version
│   ├── schema.py                       # Table DDL, triggers, indexes, FTS5
│   ├── database.py                     # Connection management, initialization, config seeding
│   ├── crud.py                         # CRUD operations for all tables
│   ├── embeddings.py                   # Sentence-transformers pipeline, cosine similarity
│   ├── context.py                      # Multi-stage context retrieval pipeline
│   ├── middleware.py                   # LLM provider adapters (Claude, OpenAI, local)
│   ├── consolidation.py               # Short→mid→long promotion, decay, feedback processing
│   ├── markdown_parser.py             # Markdown authoring: 4 doc types, file watcher
│   ├── migration.py                   # Chat import: ChatGPT, Claude, generic JSONL
│   ├── mcp_server.py                  # FastMCP server with stdio/SSE transports
│   ├── scheduler.py                   # Interval-based task runner
│   ├── sleep.py                       # Sleep-time reflection engine
│   ├── workspace_scanner.py           # Local file environment scanning
│   ├── server.py                      # HTTP server with all API endpoints
│   ├── cli.py                         # Command-line interface
│   └── static/                        # Management UI
│       ├── index.html                 # SPA shell
│       ├── css/
│       │   └── main.css               # Responsive styling
│       └── js/
│           ├── app.js                 # Router, sidebar, core UI logic
│           └── views/                 # View modules (15 views)
│               ├── dashboard.js       # Stats overview
│               ├── chat.js            # LLM chat interface with streaming
│               ├── memories.js        # Memory browser and search
│               ├── mindmap.js         # Knowledge graph visualization
│               ├── editor.js          # Markdown authoring editor
│               ├── skills.js          # Skill management
│               ├── import.js          # Chat migration wizard
│               ├── dbconsole.js       # SQL console with AI query generation
│               ├── mcp.js             # MCP server status and tools
│               ├── scheduler.js       # Scheduled task management
│               ├── settings.js        # Configuration UI
│               ├── connect.js         # LLM provider connection
│               ├── notifications.js   # Notification queue browser
│               ├── feedback.js        # Feedback review
│               └── audit.js           # Audit log viewer
├── src-tauri/                          # Tauri desktop shell (Rust)
│   ├── Cargo.toml                     # Rust dependencies
│   ├── src/main.rs                    # Sidecar spawning, health monitoring, tray
│   ├── tauri.conf.json                # App config, CSP, window settings
│   ├── icons/                         # App icons
│   └── capabilities/                  # Tauri capability definitions
└── docs/
    ├── ARCHITECTURE.md                # System architecture deep dive
    ├── ARCHITECTURE_AMENDMENTS.md     # Architecture updates
    ├── API_REFERENCE.md               # Full API endpoint reference
    ├── SCHEMA_REFERENCE.md            # Database schema details
    ├── DEVELOPMENT.md                 # Development guide
    └── AgentDB_PRD_v1.6.md            # Product requirements document
```

---

## CLI Reference

All commands accept `--db <path>` to specify the database file. Default is `agentdb.db`.

| Command | Description |
|---------|-------------|
| `init` | Create a new database with full schema |
| `init --force` | Overwrite an existing database |
| `verify` | Check that all tables exist |
| `stats` | Show row counts for all tables |
| `config list` | List all configuration values |
| `config get <key>` | Get a single config value |
| `config set <key> <value>` | Set a config value |
| `memory add <content>` | Add a short-term memory |
| `memory add <content> --source markdown_authored` | Add with specific source |
| `memory add <content> --no-embedding` | Skip embedding generation |
| `memory list short\|mid\|long` | List memories from a tier |
| `memory search <query> --tier short\|mid\|long` | Semantic search |
| `entity list` | List all entities |
| `entity list --type person` | Filter by entity type |
| `session start` | Start a new session |
| `session end <id>` | End a session |
| `serve` | Start the HTTP server |
| `serve --host 0.0.0.0 --port 9000` | Custom bind address |
| `mcp` | Start the MCP server (stdio mode) |

---

## Database Schema

Tables organized into five groups:

**Memory Tables** — `short_term_memory`, `midterm_memory`, `long_term_memory`
All three carry an `agent_id` column for multi-agent scoping. Short-term entries have TTL-based expiration. Midterm entries have confidence scores and decay weights. Long-term entries require high confidence and are validated periodically.

**Knowledge Infrastructure** — `agents`, `skills`, `skill_implementations`, `relations`, `entities`, `goals`, `tags`, `tag_assignments`
The `agents` table registers every agent that uses the system. The `relations` table is a polymorphic knowledge graph connecting any row in any table to any other row. `skills` are domain-agnostic capabilities discovered by semantic similarity at inference time. `skill_implementations` stores versioned executable code per skill.

**Workspace Awareness** — `workspaces`, `workspace_files`
Anchors the agent's understanding of local file environments.

**Operational Support** — `sessions`, `meta_config`, `llm_providers`, `contradictions`, `audit_log`, `feedback`, `context_snapshots`, `notification_queue`, `scheduled_tasks`
Sessions group interactions. Config is stored in-database for portability. The `llm_providers` table is the canonical source for LLM configuration (flat `meta_config` LLM keys are synced for backward compatibility but deprecated). Every write operation is logged to the immutable audit log. The notification queue holds proactive alerts. Scheduled tasks power interval-based automation.

**Performance** — `views`, `embeddings_cache`
Named graph projections for the mind map. Precomputed similarity scores.

All referential integrity for polymorphic associations is enforced through SQLite triggers, not application code. Cascade deletes clean up relations, tags, and feedback when content rows are removed. FTS5 virtual tables (`short_term_memory_fts`, `midterm_memory_fts`, `long_term_memory_fts`) enable BM25 keyword search.

---

## MCP Server

AgentDB exposes its memory system as MCP tools via [FastMCP](https://github.com/jlowin/fastmcp), supporting both stdio and SSE transports.

**Tools exposed:**

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

**Run via CLI:**
```bash
# stdio mode (for MCP clients like Claude Desktop)
python -m agentdb.cli mcp

# SSE mode (auto-started with the HTTP server on port 8421)
python -m agentdb.cli serve
```

**Configuration** (in `meta_config`):

| Key | Default | Description |
|-----|---------|-------------|
| `mcp_enabled` | `true` | Enable/disable MCP server |
| `mcp_transport` | `sse` | Transport mode: `stdio` or `sse` |
| `mcp_port` | `8421` | SSE server port |

---

## Configuration

System configuration lives in the `meta_config` table inside the database. LLM provider configuration lives in the `llm_providers` table (the row with `is_default = 1` is used by the middleware). Key settings:

| Key | Default | Description |
|-----|---------|-------------|
| `embedding_model` | `all-MiniLM-L6-v2` | Local embedding model (384 dimensions) |
| `consolidation_interval_seconds` | `300` | How often consolidation runs |
| `promotion_confidence_threshold` | `0.8` | Minimum confidence for midterm→long promotion |
| `clustering_similarity_threshold` | `0.85` | Cosine similarity threshold for clustering |
| `stm_default_ttl_seconds` | `3600` | Default TTL for short-term memories |
| `decay_rate_multiplier` | `1.0` | Controls how fast midterm memories decay |
| `markdown_inbox_path` | (empty) | Directory to watch for markdown files |
| `markdown_watch_enabled` | `false` | Enable/disable the file watcher |
| `bm25_enabled` | `true` | Enable BM25 keyword search in retrieval |
| `graph_traversal_enabled` | `true` | Enable graph traversal in retrieval |
| `temporal_boost_enabled` | `true` | Enable recency weighting in retrieval |
| `reranker_enabled` | `false` | Enable cross-encoder reranking |
| `sleep_idle_threshold_seconds` | `300` | Idle time before sleep processing activates |
| `sleep_reflection_enabled` | `true` | Enable sleep-time reflection |
| `scheduler_enabled` | `true` | Enable scheduled task runner |
| `db_console_write_enabled` | `false` | Allow write queries in the DB console |
| `encryption_enabled` | `false` | SQLCipher encryption at rest |

Set any value via CLI:

```bash
python -m agentdb.cli config set embedding_model all-MiniLM-L6-v2
python -m agentdb.cli config set consolidation_interval_seconds 600
```

Or via the Settings page in the management UI. LLM providers are managed through the provider management interface in Settings, not through flat config keys.

---

## Markdown Authoring

Create agent knowledge by writing markdown files with YAML frontmatter. Four document types:

**Memory** — Direct knowledge injection into long-term memory at confidence 1.0:
```markdown
---
type: memory
category: fact
tags: [hardware, pricing]
entities: [Orgill, Whitten Hardware]
---

Orgill offers 60-day net terms on hardware orders over $500.
```

**Instruction** — Behavioral directives injected into every conversation:
```markdown
---
type: instruction
priority: high
tags: [behavior]
---

Always respond in a direct, no-fluff style. Never hedge.
```

**Skill** — Capability definitions with executable code:
````markdown
---
type: skill
execution_type: code_procedure
language: python
dependencies: [requests]
---

# API Health Check

Check if an API endpoint is responding.

```python
def execute(url):
    import requests
    r = requests.get(url, timeout=10)
    return {"status": r.status_code, "ok": r.ok}
```
````

**Knowledge** — Long-form documents chunked on headings:
```markdown
---
type: knowledge
title: Vendor SOP
tags: [sop, operations]
entities: [Whitten Hardware]
---

## Ordering Process

Place orders through the portal by Wednesday for Friday delivery.

## Returns

Returns accepted within 30 days with original invoice.
```

Submit via the Markdown Editor in the UI, the `/api/markdown/submit` endpoint, or by dropping `.md` files into the configured inbox directory.

---

## Management UI

The browser-based management UI at `http://127.0.0.1:8420/` provides:

| View | Description |
|------|-------------|
| **Dashboard** | Stats overview with memory counts, entity totals, and system health |
| **Chat** | Streaming LLM conversation interface with context injection |
| **Memories** | Browse, search, and inspect memories across all three tiers |
| **Mind Map** | Interactive knowledge graph visualization |
| **Markdown Editor** | Author and submit knowledge documents |
| **Skills** | View and manage discovered capabilities |
| **Chat Import** | Migration wizard for ChatGPT, Claude, and JSONL exports |
| **DB Console** | SQL query interface with AI-assisted query generation |
| **MCP** | MCP server status, connected tools, and transport config |
| **Scheduler** | Manage interval-based automated tasks |
| **Settings** | Configure LLM providers, retrieval strategies, and system behavior |
| **Connect** | LLM provider connection and API key setup |
| **Notifications** | Browse queued proactive alerts |
| **Feedback** | Review endorsements, corrections, and annotations |
| **Audit Log** | Immutable record of all database operations |

---

## Deployment Models

**Headless mode** (available now): Run the Python backend standalone. The HTTP server, agent API, MCP server, and management UI are available on localhost. Suitable for servers, edge devices, and environments without a GUI.

**Desktop mode** (Phase 8): Tauri 2.x shell bundles the Python backend as a sidecar, manages process lifecycle, provides system tray integration with health monitoring, and auto-restarts on failure. The Tauri shell is scaffolded with sidecar spawning and health monitoring implemented.

Both modes use the identical `.db` file. A database created in one mode works in the other.

---

## Implementation Status

| Phase | Status | Scope |
|-------|--------|-------|
| 1. Foundation | Complete | Schema (24 tables + FTS5), triggers, CRUD, embeddings, CLI |
| 2. Agent Communication & MCP | Complete | MCP server, REST agent API, multi-strategy retrieval, middleware |
| 3. Consolidation Engine | Complete | STM→MTM→LTM promotion, decay, contradiction detection, feedback |
| 4. Markdown Authoring | Complete | 4 document types, chunking, deduplication, file watcher |
| 5. Migration Pipeline | Complete | ChatGPT, Claude, JSONL parsers, 5-phase pipeline |
| 6. User Interface | Complete | 15-view management SPA with chat, mind map, DB console |
| 7. Performance Engineering | In Progress | Vectorized clustering, ANN indexing, cross-encoder reranker, query optimization |
| 8. Agent Execution Layer | Scaffolded | Tauri shell, sidecar lifecycle, system tray, native dialogs |
| 9–11 | Planned | Workspace awareness, sleep-time processing, encryption hardening |

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| Database | SQLite 3 with WAL mode, FTS5, optional SQLCipher encryption |
| Backend | Python 3.11+ (no web framework — built on `http.server`) |
| Embeddings | sentence-transformers 3.3.1 / all-MiniLM-L6-v2 (384 dimensions, local) |
| Vector math | numpy 2.2.3 |
| MCP | FastMCP (mcp >= 1.0.0) with stdio and SSE transports |
| UI | Modular SPA — HTML + CSS + vanilla ES6 JavaScript (15 view modules) |
| Desktop shell | Tauri 2.x (Rust core, native webview, sidecar management) |

---

## Documentation

Detailed documentation is in the [`docs/`](docs/) directory:

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — System layers, module map, and data flows
- [API_REFERENCE.md](docs/API_REFERENCE.md) — Full HTTP endpoint reference
- [SCHEMA_REFERENCE.md](docs/SCHEMA_REFERENCE.md) — Database table definitions
- [DEVELOPMENT.md](docs/DEVELOPMENT.md) — Development setup and contribution guide
- [AgentDB_PRD_v1.6.md](docs/AgentDB_PRD_v1.6.md) — Product requirements document

---

## License

MIT LICENSE HOMIE — Sultani Investments, LLC. All rights reserved.
