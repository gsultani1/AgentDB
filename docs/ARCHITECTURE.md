# AgentDB Architecture

Technical architecture reference. Current as of v1.6 implementation.

---

## System Layers

AgentDB is composed of four layers. Each layer has a single responsibility and communicates with adjacent layers through well-defined interfaces.

```
┌─────────────────────────────────────────────────────────────┐
│                    Tauri Shell (Rust)                        │
│  Native webview, sidecar spawning, health monitoring,       │
│  system tray, auto-restart on crash, graceful shutdown      │
├─────────────────────────────────────────────────────────────┤
│                    HTML/JS UI Layer                          │
│  Modular SPA: 18 view modules, CSS custom properties,       │
│  served via HTTP or Tauri webview                           │
├─────────────────────────────────────────────────────────────┤
│                 Python Sidecar Backend                       │
│  HTTP server, agent API, operator API, MCP server (SSE),    │
│  consolidation engine, sleep-time processor, cross-encoder  │
│  reranker, skill executor, markdown parser, file processor, │
│  migration pipeline, git sync, workspace scanner,           │
│  context retrieval, LLM middleware, scheduler               │
├─────────────────────────────────────────────────────────────┤
│                   SQLite Database                            │
│  30+ tables, triggers, FTS5, WAL mode, single portable file │
│  Optional SQLCipher encryption at rest                      │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Architectural Principle: Demand-Constructed Context

AgentDB does not carry conversation history forward between turns. Every turn constructs context fresh from the database.

The middleware receives a user message, queries AgentDB for relevant memories, entities, goals, and skills via the multi-strategy retrieval pipeline, formats the results for the configured LLM provider, calls the LLM, ingests both user message and AI response into short-term memory, creates a context snapshot for audit, and returns the response. No conversation history accumulates. No compaction occurs.

This eliminates the entire class of failures that plague accumulate-and-compact systems: lost instructions, forgotten constraints, degraded recall over long sessions. A conversation on turn 500 has the same retrieval quality as turn 5.

---

## Module Map

### `schema.py` — Database Definition (1,041 lines)

All CREATE TABLE statements, CHECK constraints, trigger SQL for polymorphic referential integrity and cascade deletes, index definitions, and FTS5 virtual table creation. No runtime logic. Pure DDL.

Tables organized into five groups:
- **Memory**: `short_term_memory`, `midterm_memory`, `long_term_memory`
- **Knowledge**: `agents`, `skills`, `skill_implementations`, `relations`, `entities`, `goals`, `tags`, `tag_assignments`
- **Workspace**: `workspaces`, `workspace_files`
- **Operational**: `sessions`, `conversation_threads`, `meta_config`, `llm_providers`, `contradictions`, `audit_log`, `feedback`, `context_snapshots`, `notification_queue`, `scheduled_tasks`, `file_attachments`, `channel_configs`, `channel_messages`, `autonomous_tasks`, `task_steps`, `task_actions`, `file_access_grants`, `shell_command_log`
- **Performance**: `views`, `embeddings_cache`

### `database.py` — Initialization and Connection (314 lines)

Database creation, schema installation, trigger installation, FTS5 setup, default config seeding (80+ values), default agent creation. Provides `get_connection()` which configures WAL mode and foreign keys. Includes SQLCipher detection and passphrase handling via `AGENTDB_PASSPHRASE` environment variable. Provides `verify_schema()`, `encryption_status()`, and `rekey_database()`.

### `crud.py` — Data Access (2,250 lines)

CRUD operations for all tables. Every function takes a `sqlite3.Connection` as its first argument and returns plain dicts. No ORM. Direct SQL with parameterized queries.

Key patterns:
- `create_*` functions generate UUIDs and timestamps internally
- `list_*` functions accept optional filters, limit, and offset
- `update_*` functions accept `**kwargs` filtered against an allowed-fields set
- `delete_*` functions cascade through triggers defined in `schema.py`
- Memory create functions accept `agent_id` for multi-agent scoping
- `_sync_default_provider_to_config()` maintains backward-compatible meta_config LLM keys from `llm_providers` table

### `embeddings.py` — Vector Pipeline (166 lines)

Manages the sentence-transformers model lifecycle (lazy load, cache). Provides:
- `generate_embedding(text)` → numpy float32 array (384 dimensions)
- `generate_embeddings_batch(texts)` → batched generation
- `embedding_to_blob()` / `blob_to_embedding()` → SQLite BLOB serialization
- `cosine_similarity(a, b)` → float score using vectorized numpy normalization
- `semantic_search(query_emb, candidates, top_k)` → ranked results
- `bm25_search(query, conn, tables)` → FTS5 keyword search

The embedding model runs locally. No external API calls after initial model download.

### `context.py` — Retrieval Pipeline (513 lines)

Nine-stage multi-strategy context retrieval:

1. **Query normalization** — generate embedding via sentence-transformers
2. **Semantic vector search** — cosine similarity across all three memory tiers
3. **BM25 keyword search** — SQLite FTS5 ranking
4. **Graph traversal** — entity → relations → memories expansion
5. **Temporal weighting** — exponential recency decay (configurable curve, default 0.95)
6. **Score fusion** — 40% semantic + 25% BM25 + 20% graph + 15% temporal
7. **Cross-encoder reranking** — optional ms-marco-MiniLM-L-6-v2 (disabled by default)
8. **Pinned memory injection** — always-in-context memories at top of payload
9. **Context assembly** — labeled sections with token budget enforcement

Multi-agent scoping: `agent_id` restricts to that agent + "shared" memories. `include_agents` extends visibility.

Context snapshots are automatically captured on every retrieval, recording all memory IDs, strategies used, goals, and skills matched.

### `middleware.py` — LLM Integration (707 lines)

Provider-agnostic middleware implementing the demand-constructed context pipeline:
1. Receives user message
2. Queries AgentDB for context via `context.py`
3. Retrieves identity/directive memories
4. Formats context for the configured provider
5. Calls the LLM API
6. Ingests both user message and AI response into short-term memory
7. Creates a context snapshot for audit
8. Returns the response with full observability payload

Provider resolution priority chain:
1. Explicit `provider_id` in request
2. Agent's `default_provider_id`
3. `active_provider_id` in meta_config
4. `is_default = 1` row in `llm_providers`
5. First `is_active = 1` row

Current adapters: `ClaudeAdapter` (XML-tagged context), `OpenAIAdapter`, `LocalLLMAdapter`.

`get_llm_config()` reads from the `llm_providers` table as the canonical source.

### `consolidation.py` — Memory Lifecycle (611 lines)

Runs on a configurable interval. Four phases per cycle:

1. **Short→Midterm** — Vectorized numpy clustering: assembles all active STM embeddings into a single N×384 matrix, computes the full N×N similarity matrix via a single matrix multiplication, applies clustering threshold. Generates consolidated midterm entries from each cluster.
2. **Confidence Boosting** — Survival reward: entries alive across multiple consolidation cycles gain 0.05 per cycle (max 0.3 boost). Soft path to LTM promotion.
3. **Midterm→Long-term** — Evaluates high-confidence midterm entries (≥0.8). Checks for contradictions against existing LTM via semantic similarity. Promotes or flags for review.
4. **Decay and Pruning** — Time-based decay formula: `weight - (days_since_access × 0.01 × multiplier)`. Removes entries at zero weight. User-authored entries exempt.
5. **Feedback Processing** — Endorsements increase confidence. Corrections trigger contradiction flow. Deletion requests queue for removal. Annotations attached as relations.

### `sleep.py` — Sleep-Time Reflection (511 lines)

Activates when idle time exceeds `sleep_idle_threshold_seconds` (default 300). Five phases:

1. **Full Consolidation** — runs the entire consolidation cycle
2. **Goal Monitoring** — scans memories ingested in the last 24 hours against active goal embeddings; creates `goal_match` notifications above threshold
3. **Graph Pruning** — removes low-weight relations (default min 0.05) using JOIN-based batch operations; deletes orphaned relations; skips user-authored
4. **Custom Alert Evaluation** — 6 condition types: `entity_mention`, `contradiction_detected`, `db_size_threshold`, `content_keyword`, `goal_match`, `memory_count_threshold`. Cooldown support per rule.
5. **Cycle Notification** — summary notification with stats

### `skill_executor.py` — Skill Execution Engine (362 lines)

Executes skills in sandboxed subprocesses with resource limits:
- **code_procedure** — Python/Bash subprocess with timeout, memory cap, captured stdout/stderr
- **prompt_template** — input interpolation, LLM call, output parsing
- **composite** — chained multi-step execution
- **tool_invocation** — HTTP REST calls to external endpoints

All executions logged to `skill_executions` with inputs, outputs, duration, exit code.

### `markdown_parser.py` — Knowledge Authoring (890 lines)

Processes markdown documents with YAML frontmatter into database records:

| Document Type | Target Table | Behavior |
|---------------|-------------|----------|
| `memory` | `long_term_memory` | Direct injection at confidence 1.0, provenance "user_authored" |
| `instruction` | `long_term_memory` | Category "directive", injected into every conversation |
| `skill` | `skills` + `skill_implementations` | Extracts name, description, code blocks |
| `knowledge` | `long_term_memory` (chunked) + `entities` | Splits on h2/h3, creates parent entity, links via "chunk_of" |

YAML frontmatter parser handles flat key-value pairs, bracket-delimited lists, single-line JSON, booleans, and integers. Explicitly rejects and raises `ValueError` for multi-line values, anchors/aliases, and nested mappings.

Deduplication: embedding similarity > 0.95 with existing record → update rather than create.

`MarkdownFileWatcher` monitors configurable inbox directory with polling (default 5s interval).

### `migration.py` — Chat Import (512 lines)

Five-phase pipeline for ChatGPT (JSON tree linearization), Claude (JSON array), and generic JSONL formats. Cross-import deduplication via embedding similarity.

### `file_processor.py` — File Attachment Handling (232 lines)

Processes uploaded files (PDF via pdfminer.six, plain text, code, CSV). Extracts content, chunks it, generates embeddings, and ingests into STM.

### `git_sync.py` — Git Knowledge Sync (231 lines)

Pulls from a configured git repository, detects changed files, processes through the markdown pipeline, and records the commit hash.

### `workspace_scanner.py` — Workspace File Scanning (193 lines)

Walks registered workspaces recursively, classifies files by extension, generates embeddings for text files, tracks content hashes for change detection, creates `workspace_files` records.

### `mcp_server.py` — MCP Server (166 lines)

FastMCP server exposing 9 tools: `retrieve_context_tool`, `ingest_memory`, `search_memories`, `list_memories`, `create_entity`, `list_entities`, `check_goals`, `get_health`, `run_consolidation`. Supports SSE (port 8421, auto-started) and stdio transports.

The MCP thread runs with crash recovery: retry loop with 2-second delay, max 5 consecutive failures within 60 seconds before giving up.

### `scheduler.py` — Task Runner (274 lines)

Interval-based scheduled task execution. Supports consolidation, sleep cycles, workspace scans, integrity checks. Background thread with configurable poll interval.

### `server.py` — HTTP Server (2,258 lines)

Built on Python's `http.server`. 60+ API endpoints serving the operator API, agent API, and static UI. All responses use `{ status, data, error }` envelope. URL routing via regex pattern matching.

### `cli.py` — Command Line Interface (370 lines)

Argparse-based CLI. Subcommands: `init`, `verify`, `stats`, `config`, `memory`, `entity`, `session`, `serve`, `mcp`.

---

## Dependency Direction

```
cli.py ──→ server.py ──→ middleware.py ──→ context.py ──→ crud.py ──→ database.py ──→ schema.py
                    ├──→ markdown_parser.py ──→ crud.py      └──→ embeddings.py
                    ├──→ migration.py ──→ crud.py
                    ├──→ consolidation.py ──→ crud.py + embeddings.py
                    ├──→ sleep.py ──→ consolidation.py + crud.py
                    ├──→ skill_executor.py ──→ middleware.py + crud.py
                    ├──→ file_processor.py ──→ crud.py + embeddings.py
                    ├──→ git_sync.py ──→ markdown_parser.py
                    ├──→ workspace_scanner.py ──→ crud.py + embeddings.py
                    ├──→ scheduler.py ──→ crud.py
                    └──→ mcp_server.py ──→ context.py + crud.py
```

No circular imports. Every module depends only on modules below or beside it in this graph.

---

## Data Flow: Agent Context Retrieval

```
External AI System (MCP or REST)
        │
        ▼
  POST /api/agent/context { query: "...", agent_id: "..." }
        │
        ▼
  context.py: retrieve_context()
        │
        ├─ 1. Generate query embedding (embeddings.py)
        ├─ 2. Semantic vector search: STM, MTM, LTM (top N per tier)
        ├─ 3. BM25 keyword search (FTS5)
        ├─ 4. Entity identification + graph traversal
        ├─ 5. Temporal weighting (recency decay)
        ├─ 6. Score fusion (0.4 sem + 0.25 bm25 + 0.2 graph + 0.15 temporal)
        ├─ 7. Cross-encoder reranking (if enabled)
        ├─ 8. Pinned memory injection
        └─ 9. Context assembly with token budget
        │
        ▼
  Return ranked context payload + auto-capture context snapshot
  { memories, entities, goals, skills, strategies_used }
```

## Data Flow: Chat Pipeline

```
User Message (UI, REST, or future channel)
    │
    ▼
middleware.py: execute_chat_pipeline()
    │
    ├─ Retrieve context (context.py — full 9-stage pipeline)
    ├─ Get identity/directive memories
    ├─ Format context for provider (ClaudeAdapter → XML, OpenAI → system msg)
    ├─ Call LLM API
    ├─ Ingest user msg → STM
    ├─ Ingest AI response → STM
    ├─ Create context_snapshot (auto-captured)
    │
    ▼
Return { response, context_payload, snapshot_id, provider, model, latency }
```

## Data Flow: Consolidation Cycle

```
Timer / Manual Trigger / Sleep-Time Processor
    │
    ▼
consolidation.py: run_consolidation()
    │
    ├─ Phase 1: Cluster active STM entries (vectorized numpy N×N matrix)
    │            Generate MTM entries from clusters
    │            Mark originals as promoted
    │
    ├─ Phase 2: Boost surviving MTM confidence (+0.05/cycle, max 0.3)
    │
    ├─ Phase 3: Evaluate high-confidence MTM (≥0.8) for LTM promotion
    │            Check for contradictions against existing LTM
    │            Promote or flag for review
    │
    ├─ Phase 4: Apply time-based decay to MTM
    │            Delete zero-weight entries
    │            Skip user-authored entries
    │
    └─ Phase 5: Process pending feedback
                Endorsements → boost confidence
                Corrections → contradiction flow
                Deletions → queue removal
```

## Data Flow: Sleep-Time Processing

```
Idle Detection (>300s since last /api/agent/* call)
    │
    ▼
sleep.py: run_sleep_cycle()
    │
    ├─ Phase 1: Full consolidation cycle
    ├─ Phase 2: Goal monitoring (24h window, similarity threshold)
    ├─ Phase 3: Graph pruning (low-weight + orphaned relations)
    ├─ Phase 4: Custom alert evaluation (6 condition types)
    └─ Phase 5: Summary notification
    │
    ▼
Deactivates within 10s of any new /api/agent/* call
```

---

## Trigger-Based Integrity

SQLite triggers enforce referential integrity for polymorphic associations, keeping all behavioral logic inside the database file.

**Insert Validation**: BEFORE INSERT triggers on `relations`, `tag_assignments`, `feedback`, and `pinned_memories` verify that the referenced polymorphic ID exists in its declared table using CASE expressions.

**Cascade Deletes**: AFTER DELETE triggers on all content tables clean up associated rows in `relations`, `tag_assignments`, `feedback`, and `pinned_memories`. Additional cascades: `skills` → `skill_implementations` + `skill_executions`, `workspaces` → `workspace_files`, `tags` → `tag_assignments`, `conversation_threads` → `file_attachments`, `providers` → SET NULL on sessions/agents/snapshots.

---

## Multi-Agent Scoping

All three memory tables carry an `agent_id` column (default: `"default"`). The `agents` table registers every agent with per-agent config overrides and a `default_provider_id`.

- Agent sees its own memories + anything with `agent_id = "shared"`
- Cross-agent queries require explicit `include_agents` parameter
- The operator sees all agents through the management UI
- Each agent can default to a different LLM provider

---

## Embedding Model

- **Model**: `all-MiniLM-L6-v2` via sentence-transformers
- **Dimensions**: 384 (float32)
- **Storage**: Raw bytes in SQLite BLOB columns
- **Search**: In-memory cosine similarity (vectorized numpy)
- **Runs locally**: No external API calls after initial model download (~90 MB)
- **Lazy loading**: Model cached for process lifetime after first use
- **Batch encoding**: Available for bulk operations via `generate_embeddings_batch()`

## Cross-Encoder Reranker

- **Model**: `cross-encoder/ms-marco-MiniLM-L-6-v2` via sentence-transformers
- **Purpose**: Reranks retrieval candidates for higher precision
- **Loading**: Lazy-loaded on first reranking call (not pre-warmed)
- **Config**: Disabled by default (`reranker_enabled = "false"`)
- **Integration**: Stage 7 of the retrieval pipeline, after score fusion, before top-K selection

---

## Tauri Desktop Shell

The `src-tauri/` directory contains a Tauri 2.x desktop wrapper:

- **Sidecar spawning**: Launches the Python HTTP server via `agentdb.cli serve`
- **Health monitoring**: Checks `/api/health` periodically; restarts sidecar after consecutive failures
- **System tray**: Menu with show, health check, restart, and quit options
- **Auto-init**: Creates database if missing on first launch
- **Native webview**: Loads the management UI from the sidecar's HTTP server

The Rust layer contains no business logic. All intelligence lives in Python.
