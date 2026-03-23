# AgentDB Architecture

Technical architecture reference for AgentDB v1.4.

---

## System Layers

AgentDB is composed of four layers. Each layer has a single responsibility and communicates with adjacent layers through well-defined interfaces.

```
┌─────────────────────────────────────────────────────┐
│                  Tauri Shell (Phase 7)               │
│  Native webview, sidecar management, system tray     │
├─────────────────────────────────────────────────────┤
│                  HTML/JS UI Layer                     │
│  Single-file SPA served via HTTP or Tauri webview    │
├─────────────────────────────────────────────────────┤
│               Python Sidecar Backend                 │
│  HTTP server, agent API, operator API, MCP server,   │
│  consolidation, markdown parser, migration, context  │
│  retrieval, LLM middleware, file watcher             │
├─────────────────────────────────────────────────────┤
│                 SQLite Database                       │
│  23 tables, triggers, FTS5, WAL mode, single file    │
└─────────────────────────────────────────────────────┘
```

---

## Module Map

### `schema.py` — Database Definition

Defines all 23 CREATE TABLE statements, CHECK constraints, trigger SQL for polymorphic referential integrity and cascade deletes, index definitions, and FTS5 virtual table creation statements. No runtime logic. Pure DDL.

Tables are organized into five groups:
- **Memory**: `short_term_memory`, `midterm_memory`, `long_term_memory`
- **Knowledge**: `agents`, `skills`, `skill_implementations`, `relations`, `entities`, `goals`, `tags`, `tag_assignments`
- **Workspace**: `workspaces`, `workspace_files`
- **Operational**: `sessions`, `meta_config`, `contradictions`, `audit_log`, `feedback`, `context_snapshots`, `notification_queue`
- **Performance**: `views`, `embeddings_cache`

### `database.py` — Initialization and Connection

Handles database creation, schema installation, trigger installation, FTS5 setup, default config seeding (35 values), and default agent creation. Provides `get_connection()` which configures WAL mode and foreign keys. Provides `verify_schema()` for health checks.

### `crud.py` — Data Access

CRUD operations for all 23 tables. Every function takes a `sqlite3.Connection` as its first argument and returns plain dicts. No ORM. No abstraction layers. Direct SQL with parameterized queries.

Key patterns:
- `create_*` functions generate UUIDs and timestamps internally
- `list_*` functions accept optional filters, limit, and offset
- `update_*` functions accept `**kwargs` filtered against an allowed-fields set
- `delete_*` functions cascade through triggers defined in `schema.py`
- Memory create functions accept `agent_id` for multi-agent scoping

### `embeddings.py` — Vector Pipeline

Manages the sentence-transformers model lifecycle (lazy load, cache). Provides:
- `generate_embedding(text)` → numpy float32 array (384 dimensions)
- `generate_embeddings_batch(texts)` → batched generation
- `embedding_to_blob()` / `blob_to_embedding()` → SQLite BLOB serialization
- `cosine_similarity(a, b)` → float score
- `semantic_search(query_emb, candidates, top_k)` → ranked results

The embedding model runs locally. No external API calls.

### `context.py` — Retrieval Pipeline

Implements the multi-stage context retrieval described in PRD Section 6.3:

1. Generate query embedding
2. Cosine similarity search across all three memory tiers (top N per tier)
3. Entity identification via embedding similarity + relation expansion
4. Goal matching against active goal embeddings
5. Skill matching against skill description embeddings

Returns a unified payload: `{ memories, entities, goals, skills }`.

Planned additions (Phase 10): BM25 keyword search via FTS5, graph traversal, temporal weighting, cross-encoder reranking.

### `middleware.py` — LLM Integration

Provider-agnostic middleware that:
1. Receives a user message
2. Queries AgentDB for context via `context.py`
3. Retrieves identity/directive memories
4. Formats context for the configured provider
5. Calls the LLM API
6. Ingests both user message and AI response into short-term memory
7. Creates a context snapshot for audit
8. Returns the response with full observability payload

Provider adapters implement two methods:
- `format_context(payload)` → provider-specific string
- `call_provider(messages, context, config)` → AI response text

Current adapters: `ClaudeAdapter`, `OpenAIAdapter`, `LocalLLMAdapter`.

### `consolidation.py` — Memory Lifecycle

Runs on a configurable interval. Four phases per cycle:

1. **Short→Midterm**: Cluster semantically similar active STM entries, generate consolidated midterm entries, mark originals as promoted.
2. **Midterm→Long-term**: Evaluate high-confidence midterm entries. Check for contradictions against existing LTM. Promote or flag.
3. **Decay and Pruning**: Reduce decay weights on unaccessed midterm entries. Delete entries at zero weight. Flag stale long-term entries. User-authored entries are exempt.
4. **Feedback Processing**: Apply endorsements (boost confidence), corrections (create contradictions), deletion requests, and annotations.

`ConsolidationScheduler` runs cycles in a background thread.

### `markdown_parser.py` — Knowledge Authoring

Processes markdown documents with YAML frontmatter into database records:

| Document Type | Target Table | Behavior |
|---------------|-------------|----------|
| `memory` | `long_term_memory` | Direct injection at confidence 1.0, provenance "user_authored" |
| `instruction` | `long_term_memory` | Category "directive", injected into every conversation |
| `skill` | `skills` + `skill_implementations` | Extracts name, description, code blocks |
| `knowledge` | `long_term_memory` (chunked) + `entities` | Splits on h2/h3, creates parent document entity, links chunks via "chunk_of" relations |

Deduplication: If embedding similarity > 0.95 with an existing record, the system updates rather than creates.

`MarkdownFileWatcher` monitors a configurable inbox directory, processes new `.md` files, and moves them to `processed/` or `failed/` subdirectories.

### `migration.py` — Chat Import

Five-phase pipeline for importing external chat histories:

1. **Ingestion**: Parse provider-specific format (ChatGPT tree linearization, Claude, generic JSONL), create sessions and STM entries with status "imported"
2. **Consolidation**: Group imported messages by session, create midterm summaries
3. **Promotion**: Identify repeated patterns, boost confidence, promote to LTM
4. **Graph Construction**: Link memories to sessions via relations
5. **User Review**: Flag low-confidence entries and contradictions for operator review

### `server.py` — HTTP Server

Built on Python's `http.server`. No framework dependency. Serves:

- Static UI at `/` (single-file HTML from `static/index.html`)
- Operator API at `/api/*` (management UI backend)
- Agent API at `/api/agent/*` (external AI system interface)

All responses use `{ status, data, error }` envelope. CORS headers allow localhost access. URL routing uses regex pattern matching for parameterized paths.

Full CRUD endpoints exist for memories, skills, entities, goals, agents, notifications, config, feedback, contradictions, views, and workspaces.

### `cli.py` — Command Line

Argparse-based CLI. Subcommands: `init`, `verify`, `stats`, `config`, `memory`, `entity`, `session`, `serve`. Entry point: `python -m agentdb.cli`.

---

## Data Flow: Agent Context Retrieval

```
External AI System
        │
        ▼
  POST /api/agent/context { query: "..." }
        │
        ▼
  context.py: retrieve_context()
        │
        ├─ Generate query embedding (embeddings.py)
        ├─ Cosine search: STM, MTM, LTM (top N per tier)
        ├─ Entity identification + relation expansion (crud.py)
        ├─ Goal matching against active goals
        └─ Skill matching against skill descriptions
        │
        ▼
  Return ranked context payload
  { memories: {short_term, midterm, long_term},
    entities: [...], goals: [...], skills: [...] }
```

## Data Flow: Chat Pipeline

```
User Message
    │
    ▼
middleware.py: execute_chat_pipeline()
    │
    ├─ Retrieve context (context.py)
    ├─ Get identity/directive memories
    ├─ Format context for provider (adapter)
    ├─ Call LLM API
    ├─ Ingest user msg → STM
    ├─ Ingest AI response → STM
    ├─ Create context_snapshot
    │
    ▼
Return { response, context_payload, snapshot_id, latency }
```

## Data Flow: Markdown Authoring

```
Markdown Document (UI editor / file watcher / API)
    │
    ▼
markdown_parser.py: process_markdown_document()
    │
    ├─ Parse YAML frontmatter
    ├─ Validate by document type
    ├─ Extract body content
    ├─ Generate embeddings
    ├─ Check for duplicates (>0.95 similarity → update)
    ├─ Create database records (LTM / skills / entities)
    ├─ Create relations + tag assignments
    ├─ Log to audit_log
    │
    ▼
Return creation summary
```

---

## Trigger-Based Integrity

SQLite triggers enforce referential integrity for polymorphic associations. This keeps all behavioral logic inside the database file rather than in application code.

**Insert Validation**: BEFORE INSERT triggers on `relations`, `tag_assignments`, and `feedback` verify that the referenced polymorphic ID exists in its declared table using CASE expressions.

**Cascade Deletes**: AFTER DELETE triggers on all content tables clean up associated rows in `relations`, `tag_assignments`, and `feedback`. Additional cascades: `skills` → `skill_implementations`, `workspaces` → `workspace_files`, `tags` → `tag_assignments`.

---

## Multi-Agent Scoping

All three memory tables carry an `agent_id` column (default: "default"). The `agents` table registers every agent with per-agent config overrides.

- Agent sees its own memories + anything with `agent_id = "shared"`
- Cross-agent queries require explicit `include_agents` parameter
- The operator sees all agents through the management UI

---

## Embedding Model

- **Model**: `all-MiniLM-L6-v2` via sentence-transformers
- **Dimensions**: 384 (float32)
- **Storage**: Raw bytes in SQLite BLOB columns
- **Search**: In-memory cosine similarity (no vector database dependency)
- **Runs locally**: No external API calls after initial model download

The model is lazy-loaded on first use and cached for the process lifetime. Batch encoding is available for bulk operations.
