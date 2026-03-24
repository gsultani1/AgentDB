# AgentDB

A sovereign, local-first agent memory system with tiered knowledge, an empirical knowledge graph, MCP-native agent communication, multi-agent support, markdown authoring, and external chat migration.

**MIT License — Sultani Investments, LLC**

---

## What It Does

AgentDB gives AI agents persistent, structured memory. It stores what the agent learns across conversations, organizes it into short-term, midterm, and long-term tiers, and retrieves the most relevant context when the agent needs it. The entire system lives in a single portable SQLite file.

- **Tiered memory** with automatic promotion, decay, and consolidation
- **Knowledge graph** connecting memories, entities, skills, and goals through typed relations
- **Multi-agent support** with scoped memory access per agent
- **Semantic search** using locally-generated embeddings (no API calls)
- **Multi-strategy retrieval** combining vector similarity, BM25 keyword search, graph traversal, and temporal weighting
- **Markdown authoring** for direct knowledge injection via files or a built-in editor
- **Chat migration** from ChatGPT, Claude, and generic JSONL exports
- **Provider-agnostic LLM middleware** with adapters for Claude, OpenAI, and local LLMs
- **Full audit trail** of every operation on every table
- **Single-file portability** — copy the `.db` file to any machine and it works

## Quick Start

### Prerequisites

- Python 3.11+
- Git

### Setup

```bash
git clone https://github.com/your-org/AgentDB.git
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

This creates `agentdb.db` in the current directory with all 23 tables, triggers, indexes, FTS5 virtual tables, 35 default configuration values, and a default agent.

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

- **Operator API**: `http://127.0.0.1:8420/api/`
- **Agent API**: `http://127.0.0.1:8420/api/agent/`
- **Management UI**: `http://127.0.0.1:8420/`

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
├── requirements.txt
├── .gitignore
├── docs/
│   ├── AgentDB_PRD_v1.4.md        # Product requirements document
│   ├── ARCHITECTURE.md             # System architecture deep dive
│   └── API_REFERENCE.md            # Full API endpoint reference
├── agentdb/
│   ├── __init__.py                 # Package init, version
│   ├── schema.py                   # All 23 table DDL, triggers, indexes, FTS5
│   ├── database.py                 # Connection management, initialization, config seeding
│   ├── crud.py                     # CRUD operations for all 23 tables
│   ├── embeddings.py               # Sentence-transformers pipeline, cosine similarity
│   ├── context.py                  # Multi-stage context retrieval pipeline
│   ├── middleware.py               # LLM provider adapters (Claude, OpenAI, local)
│   ├── consolidation.py            # Short→mid→long promotion, decay, feedback processing
│   ├── markdown_parser.py          # Markdown authoring: 4 doc types, file watcher
│   ├── migration.py                # Chat import: ChatGPT, Claude, generic JSONL
│   ├── server.py                   # HTTP server with all API endpoints + static UI
│   ├── cli.py                      # Command-line interface
│   └── static/
│       └── index.html              # Single-file management UI (HTML/CSS/JS)
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

---

## Database Schema

23 tables organized into five groups:

**Memory Tables** — `short_term_memory`, `midterm_memory`, `long_term_memory`
All three carry an `agent_id` column for multi-agent scoping. Short-term entries have TTL-based expiration. Midterm entries have confidence scores and decay weights. Long-term entries require high confidence and are validated periodically.

**Knowledge Infrastructure** — `agents`, `skills`, `skill_implementations`, `relations`, `entities`, `goals`, `tags`, `tag_assignments`
The `agents` table registers every agent that uses the system. The `relations` table is a polymorphic knowledge graph connecting any row in any table to any other row. `skills` are domain-agnostic capabilities discovered by semantic similarity at inference time. `skill_implementations` stores versioned executable code per skill.

**Workspace Awareness** — `workspaces`, `workspace_files`
Anchors the agent's understanding of local file environments.

**Operational Support** — `sessions`, `meta_config`, `contradictions`, `audit_log`, `feedback`, `context_snapshots`, `notification_queue`
Sessions group interactions. Config is stored in-database for portability. Every write operation is logged to the immutable audit log. The notification queue holds proactive alerts.

**Performance** — `views`, `embeddings_cache`
Named graph projections for the mind map. Precomputed similarity scores.

All referential integrity for polymorphic associations is enforced through SQLite triggers, not application code. Cascade deletes clean up relations, tags, and feedback when content rows are removed.

---

## Configuration

All configuration lives in the `meta_config` table inside the database. Key settings:

| Key | Default | Description |
|-----|---------|-------------|
| `llm_provider` | `claude` | LLM backend: claude, openai, local |
| `llm_model` | `claude-sonnet-4-20250514` | Model identifier |
| `llm_api_key` | (empty) | API key for the configured provider |
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
| `encryption_enabled` | `false` | SQLCipher encryption at rest |

Set any value via CLI:

```bash
python -m agentdb.cli config set llm_provider openai
python -m agentdb.cli config set llm_api_key sk-your-key-here
```

Or via the Settings page in the management UI.

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
```markdown
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
```

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

## Deployment Models

**Desktop mode** (planned Phase 7): Tauri executable bundles the Python sidecar, manages process lifecycle, and provides native system tray integration.

**Headless mode** (available now): Run the Python backend standalone. The agent API and management UI are available on localhost. Suitable for servers, edge devices, and environments without a GUI.

Both modes use the identical `.db` file. A database created in one mode works in the other.

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| Database | SQLite 3 with WAL mode |
| Backend | Python 3.11+ |
| Embedding Model | all-MiniLM-L6-v2 (384 dimensions, local) |
| UI | Single-file HTML + inline CSS + vanilla ES6 JavaScript |
| LLM Middleware | Provider adapters for Claude, OpenAI, local LLMs |
| Planned Shell | Tauri 2.x (Rust core, native webview) |

---

## License

Proprietary — Sultani Investments, LLC. All rights reserved.
