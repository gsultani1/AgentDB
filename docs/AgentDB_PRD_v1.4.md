# PRODUCT REQUIREMENTS DOCUMENT

# AgentDB

**A Sovereign Agent Memory System with Tiered Knowledge, Empirical Knowledge Graph, MCP-Native Agent Communication, Multi-Agent Support, Asynchronous Memory Processing, Markdown Authoring, and External Chat Migration**

---

**Prepared by George Sultani | Sultani Investments, LLC | March 2026**

| Attribute | Detail |
|-----------|--------|
| Version | 1.4 |
| Status | Draft |
| Owner | George Sultani |
| Target Platform | Tauri (Rust) / SQLite / Python Sidecar / HTML+Vanilla JS |
| Deployment Model | Local-first desktop executable with single-file portable database |
| License | Proprietary — Sultani Investments, LLC |

---

## 1. Executive Summary

AgentDB is a sovereign, local-first agent memory system built on SQLite and distributed as a Tauri desktop executable. It provides AI agents with tiered episodic memory (short-term, midterm, and long-term), domain-agnostic skills with versioned executable implementations, an empirical knowledge graph, workspace awareness, goal tracking, and full audit capabilities. The entire memory system lives in a single portable .db file that carries its own configuration, behavioral triggers, and integrity enforcement. The database supports optional encryption at rest via SQLCipher for deployments where physical device security is a concern.

The system exposes two distinct interfaces: a human-facing management UI for memory inspection, mind-map visualization, feedback, and contradiction resolution; and an MCP-native agent API that any MCP-compatible AI system can plug into directly, alongside traditional REST endpoints for systems that prefer direct HTTP integration. Multi-agent support allows multiple agents to share a single AgentDB instance with scoped memory access, enabling teams of specialized agents (email, code, research, operations) to maintain both private and shared knowledge. A built-in chat console within the Tauri application provides full observability into the memory-augmented conversation pipeline, showing exactly what context is retrieved, what skills are matched, and what gets stored after each exchange.

The retrieval engine uses multi-strategy search combining semantic vector similarity, BM25 keyword matching via SQLite FTS5, graph traversal through the relations table, and temporal weighting, with cross-encoder reranking to produce the most relevant context for each query. An asynchronous sleep-time processing system actively reorganizes and strengthens the knowledge graph during idle periods, running reflection cycles that consolidate patterns, pre-compute likely retrievals for recurring contexts, and strengthen or prune graph connections without adding latency to active conversations.

The system supports direct knowledge authoring through markdown. The operator can write memories, behavioral instructions, skill definitions, and knowledge documents in markdown format, either through a built-in editor or by dropping files into a watched directory. This gives the operator full control over the agent's knowledge base without touching SQL or application code, and enables version-controlled agent knowledge through external git repositories.

A proactive notification system monitors incoming information against active goals and operator-defined alert conditions, surfacing relevant events through the Tauri system tray without requiring the operator to query the system.

The system also provides a migration pipeline for importing external chat histories from providers like ChatGPT and Claude, converting raw conversations into structured, searchable, and semantically-linked agent knowledge.

AgentDB is designed for edge deployment, cloud independence, and full data sovereignty. No external APIs are required for core memory operations. Embeddings are generated locally. The database file is the single source of truth and can be transferred between devices without any dependency resolution. The Tauri executable bundles the UI, the Python sidecar backend, and all process management into a single distributable package, while the Python backend remains independently runnable for headless and edge deployments.

---

## 2. Goals and Non-Goals

### 2.1 Goals

Provide AI agents with a structured, tiered memory system that supports promotion, decay, consolidation, and contradiction resolution across short-term, midterm, and long-term knowledge stores.

Store domain-agnostic skills that the agent discovers applicability for at inference time through semantic similarity rather than hardcoded domain bindings, with versioned executable implementations stored separately for clean rollback and dependency tracking.

Maintain an empirical knowledge graph through a polymorphic relations table that connects any record in any table to any other record, with typed edges and weights.

Enforce referential integrity through SQLite triggers rather than application-layer code, keeping all behavioral logic inside the database file.

Expose an agent-facing API through both MCP (Model Context Protocol) and REST endpoints, enabling any MCP-compatible agent framework or direct HTTP client to retrieve contextual memories, match skills, check goals, and ingest new observations without writing custom adapters.

Support multiple agents sharing a single AgentDB instance with scoped memory access, allowing teams of specialized agents to maintain private knowledge while sharing common organizational memory through agent_id-based access control.

Provide a provider-agnostic middleware integration pattern so the memory system works identically whether the AI backend is Claude, ChatGPT, a local LLM, or a custom model.

Include a built-in chat console with full observability into memory retrieval, skill matching, goal checking, and ingestion, serving as both a test interface and a transparency tool for the human operator.

Implement multi-strategy retrieval combining semantic vector search, BM25 keyword matching, graph traversal, and temporal weighting with cross-encoder reranking to maximize retrieval accuracy across diverse query types.

Run asynchronous sleep-time memory processing during idle periods, including reflection cycles that consolidate patterns, strengthen or prune graph connections, and pre-compute likely retrievals for recurring contexts without adding latency to active conversations.

Surface proactive notifications when incoming information matches active goals or operator-defined alert conditions, delivered through the Tauri system tray or headless webhook endpoints.

Support optional encryption at rest via SQLCipher for deployments where the database file is a high-value target, particularly on edge devices subject to physical theft risk.

Enable direct knowledge authoring through markdown, allowing the operator to create memories, behavioral instructions, skill definitions, and knowledge documents through a built-in editor or a watched file directory, with support for version-controlled knowledge via external git repositories.

Provide a browser-based and Tauri-native UI for human operators to browse memories, inspect the knowledge graph as a radial mind map, provide feedback, resolve contradictions, and audit agent decisions.

Enable migration of external chat histories from ChatGPT, Claude, and other providers into the structured memory system through a five-phase pipeline.

Package the entire system as a Tauri desktop executable that manages the Python sidecar lifecycle, while preserving the ability to run the Python backend independently for headless and edge deployments.

Maintain full portability as a single SQLite file with self-contained configuration, triggers, and schema.

### 2.2 Non-Goals

Multi-tenant SaaS deployment. AgentDB supports multiple agents per instance but is designed for a single operator. Multi-tenant isolation with separate operator accounts is out of scope.

Cloud synchronization or hosted database backends. The system is local-first by design.

Real-time streaming ingestion from external chat providers. Migration is a batch process run on exported data files.

Replacing the AI provider's own interface. The built-in chat console is an observability and testing tool, not a full-featured chat client.

Hosting the agent API on a public network. All endpoints are localhost-only by default.

Full-featured markdown editor with live preview, plugins, or extension support. The built-in editor is a functional textarea with basic preview, not a replacement for dedicated editors like Obsidian or VS Code.

Export or migration tooling for moving AgentDB data to competing memory systems. The focus is on importing knowledge into AgentDB, not facilitating departure from it.

---

## 3. System Architecture

### 3.1 Core Components

The system is composed of four layers: the SQLite database layer (optionally encrypted via SQLCipher) containing all tables, triggers, views, and configuration; the Python sidecar backend providing all read/write operations, consolidation jobs, sleep-time reflection cycles, embedding generation, multi-strategy retrieval, migration pipelines, markdown parsing, file watching, MCP server, and both the operator API and agent API; the HTML/JS UI layer for human inspection, management, markdown authoring, and the chat console; and the Tauri shell providing native desktop packaging, sidecar process management, filesystem access, system tray notifications, and OS integration.

### 3.2 Technology Stack

| Component | Technology |
|-----------|------------|
| Desktop Shell | Tauri 2.x (Rust core, native webview) |
| Database | SQLite 3 with WAL mode, optional SQLCipher encryption at rest |
| Backend / Sidecar | Python 3.11+ (sqlite3, sentence-transformers, http.server or Flask) |
| Embedding Model | all-MiniLM-L6-v2 (384 dimensions, runs locally, no API calls) |
| Reranker | Cross-encoder model (e.g., cross-encoder/ms-marco-MiniLM-L-6-v2) for multi-strategy result fusion |
| UI | Single-file HTML with inline CSS and vanilla ES6 JavaScript |
| MCP Server | Python MCP server exposing agent memory operations as MCP tools |
| Agent API | JSON REST endpoints on localhost as fallback for non-MCP clients |
| Operator API | JSON REST endpoints on localhost, called by the management UI |
| Chat Console | Built into the Tauri UI, routes through middleware to any configured LLM provider |
| LLM Middleware | Python module that injects AgentDB context into provider API calls |
| Markdown Parser | Python module parsing markdown with YAML frontmatter into structured database entries |
| File Watcher | Python watchdog or polling-based directory monitor for markdown inbox processing |
| Chat Import Parsers | Python scripts per provider (ChatGPT JSON, Claude export format) |
| Integrity Enforcement | SQLite triggers for polymorphic referential integrity and cascade cleanup |
| Notifications | Tauri system tray alerts (desktop) / webhook POST (headless) |

### 3.3 Deployment Models

Desktop mode: The Tauri executable launches the Python sidecar, serves the UI through its native webview, and manages process lifecycle including startup, health monitoring, restart on crash, and clean shutdown. The operator interacts through the native window. This is the primary distribution model for desktop and laptop use.

Headless mode: The Python backend runs independently as a standalone process without Tauri. The agent API and operator API are available on localhost. The operator can connect a browser to the operator API for the management UI, or interact entirely through the CLI. This mode is for edge devices, servers, and any environment where a desktop GUI is unnecessary or unavailable.

In both modes, the SQLite database file is identical and interchangeable. A database created in desktop mode works in headless mode and vice versa.

### 3.4 Tauri Architecture Details

The Tauri Rust core is responsible for spawning the Python sidecar on application launch using Tauri's built-in sidecar support. The Rust layer monitors the sidecar process health with a heartbeat check against the Python API's /api/health endpoint. If the sidecar becomes unresponsive, Tauri restarts it automatically and the UI displays a brief reconnection indicator. On application quit, Tauri sends a graceful shutdown signal to the sidecar and waits for confirmation before exiting.

Tauri's Rust layer also provides native file dialogs for chat export imports (drag-and-drop or file picker), database file selection and backup, workspace directory selection, and markdown file selection for the authoring workflow. These filesystem operations pass paths to the Python sidecar via the existing API endpoints. The Rust layer does not contain any business logic or data access code. All intelligence lives in Python.

The UI is served through Tauri's native webview, not a bundled browser engine. This keeps the executable size small (typically under 10MB for the shell itself, plus the Python sidecar and embedding model). System tray integration allows the application to run in the background with the agent API always available for external AI systems to call.

---

## 4. Database Schema

The schema consists of twenty-three tables organized into five functional groups: memory storage, knowledge infrastructure, workspace awareness, operational support, and performance optimization. All embedding vectors are generated from the same model and stored as blobs for cross-table semantic search consistency.

### 4.1 Memory Tables

#### 4.1.1 short_term_memory

The agent's immediate working context. High write frequency, aggressive pruning. Entries are either promoted to midterm, expired by TTL, or archived.

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID, unique identifier |
| agent_id | TEXT | Identifier for the agent that created this entry. Enables multi-agent scoping. Defaults to "default" for single-agent setups |
| timestamp | DATETIME | When the entry was created |
| source | TEXT | Input channel: conversation, tool_output, sensor, chatgpt_import, claude_import, markdown_authored |
| content | TEXT | Raw text of the observation or interaction fragment |
| embedding | BLOB | Vector embedding (384-dim float32 array) |
| ttl_seconds | INTEGER | Time-to-live before automatic expiration |
| session_id | TEXT FK | References sessions.id |
| status | TEXT | active / promoted / expired / imported |

#### 4.1.2 midterm_memory

Consolidated observations that survived initial triage. Subject to confidence-based promotion and time-based decay.

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| agent_id | TEXT | Agent that owns this memory. Enables scoped retrieval in multi-agent setups |
| created_at | DATETIME | When the consolidated entry was created |
| last_accessed | DATETIME | Last retrieval timestamp, used for decay calculations |
| content | TEXT | Consolidated text |
| embedding | BLOB | Vector embedding |
| confidence | REAL | 0.0 to 1.0, reflects reinforcement count |
| source_ids | JSON | Array of short_term_memory IDs this was consolidated from |
| entity_ids | JSON | Array of entity IDs extracted from content |
| decay_weight | REAL | Decreases over time unless accessed or reinforced |
| category | TEXT | observation / pattern / inference |

#### 4.1.3 long_term_memory

Bedrock knowledge. Rarely written, heavily read. High confidence threshold for entry. Periodic validation against recent evidence.

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| agent_id | TEXT | Agent that owns this memory. "shared" for organizational knowledge accessible to all agents |
| created_at | DATETIME | When the knowledge was committed |
| last_validated | DATETIME | Last time the agent confirmed this still holds true |
| content | TEXT | The knowledge as text |
| embedding | BLOB | Vector embedding |
| confidence | REAL | Should be high (>0.8) for anything stored here |
| provenance | JSON | Chain of short-term and midterm IDs that produced this, or "user_authored" / "markdown_import" |
| entity_ids | JSON | Array of referenced entity IDs |
| category | TEXT | fact / relationship / preference / procedure / identity / directive |

### 4.2 Knowledge Infrastructure

#### 4.2.1 agents

Registry of all agents that interact with this AgentDB instance. Enables scoped memory access and cross-agent knowledge sharing. Single-agent setups use a default agent row created at initialization.

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | Agent identifier (e.g., "default", "email-agent", "code-agent", "research-agent") |
| name | TEXT | Human-readable agent name |
| description | TEXT | What this agent does |
| created_at | DATETIME | When the agent was registered |
| last_active | DATETIME | Last time this agent called the agent API |
| config | JSON | Agent-specific configuration overrides (retrieval preferences, context limits, provider settings) |

#### 4.2.2 skills

Domain-agnostic capability definitions. No domain coupling in the record itself. The agent discovers applicability through semantic similarity between the skill description embedding and the current task context. This table is optimized for discovery and retrieval during inference and does not contain executable code.

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| name | TEXT | Human-readable skill name |
| description | TEXT | Plain language description of what the skill does |
| embedding | BLOB | Vector generated from description for semantic matching |
| input_schema | JSON | What the skill expects as input |
| output_schema | JSON | What the skill produces as output |
| version | INTEGER | Current version number, incremented on updates |
| created_at | DATETIME | When the skill was first registered |
| last_used | DATETIME | Last time the agent invoked this skill |
| use_count | INTEGER | Total invocation count |
| success_rate | REAL | Success rate tracked over time |
| execution_type | TEXT | prompt_template / code_procedure / tool_invocation / composite |

#### 4.2.3 skill_implementations

Versioned executable code for each skill, stored separately from the skill definition to keep the skills table lightweight for semantic search. Multiple versions are retained for rollback capability. Only one version per skill is active at any time. Composite skills may have multiple implementation rows with an ordering column for sub-step orchestration.

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| skill_id | TEXT FK | References skills.id |
| version | INTEGER | Matches the skill version this implementation serves |
| language | TEXT | python / bash / prompt_template / javascript / composite |
| code | TEXT | Full source text of the executable implementation |
| content_hash | TEXT | SHA-256 of the code for change detection |
| dependencies | JSON | Array of required packages, modules, or external tools |
| created_at | DATETIME | When this implementation version was created |
| is_active | BOOLEAN | Whether this is the currently live implementation |
| execution_order | INTEGER | Optional: ordering for composite skill sub-steps |

#### 4.2.4 relations

Polymorphic knowledge graph backbone. Connects any row in any table to any other row in any other table. Referential integrity enforced via SQLite triggers, not foreign key constraints.

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| source_id | TEXT | ID of the source record |
| source_table | TEXT | Table name where source lives |
| target_id | TEXT | ID of the target record |
| target_table | TEXT | Table name where target lives |
| edge_type | TEXT | derived_from / contradicts / reinforces / applied_to / related_to / imports / configures / tests / documents / chunk_of |
| weight | REAL | Importance ranking for traversal and display |
| created_at | DATETIME | When the relation was established |
| context | TEXT | Optional: why this relation was created |

#### 4.2.5 entities

Normalized registry of every named entity the agent encounters. Single source for answering "what does the agent know about X" across all memory tiers and skill history.

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| canonical_name | TEXT | Primary name for the entity |
| entity_type | TEXT | person / company / project / location / concept |
| embedding | BLOB | Vector embedding of canonical name and context |
| first_seen | DATETIME | First encounter timestamp |
| last_seen | DATETIME | Most recent encounter timestamp |
| aliases | JSON | Array of alternate names or references |

#### 4.2.6 goals

Active objectives that enable proactive behavior. The agent matches incoming information against goal embeddings to surface relevant connections without being prompted.

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| description | TEXT | What the agent is trying to achieve |
| embedding | BLOB | Vector for semantic matching against incoming context |
| priority | INTEGER | Rank ordering among active goals |
| status | TEXT | active / completed / paused / abandoned |
| created_at | DATETIME | When the goal was established |
| deadline | DATETIME | Optional target completion date |
| parent_goal_id | TEXT FK | Self-referencing for hierarchical decomposition |
| completed_at | DATETIME | Optional completion timestamp |

#### 4.2.7 tags

Lightweight categorical layer complementing semantic embeddings. Hard categorical filtering when vector similarity thresholds are insufficient.

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| name | TEXT UNIQUE | Tag label |
| color | TEXT | Optional hex color for UI rendering |

#### 4.2.8 tag_assignments

Many-to-many join table linking tags to any row in any table.

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| tag_id | TEXT FK | References tags.id |
| target_id | TEXT | ID of the tagged record |
| target_table | TEXT | Table name of the tagged record |

### 4.3 Workspace Awareness

#### 4.3.1 workspaces

Anchors the agent's understanding of local environments. Multiple workspaces can be active simultaneously.

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| name | TEXT | Human-readable workspace name |
| root_path | TEXT | Absolute path to workspace root |
| workspace_type | TEXT | codebase / project_folder / data_directory |
| created_at | DATETIME | When the workspace was registered |
| last_scanned | DATETIME | Last full scan timestamp |
| metadata | JSON | Detected language, framework, build system, etc. |

#### 4.3.2 workspace_files

Maps every file and directory within a workspace. Content hashes enable change detection without full re-reads.

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| workspace_id | TEXT FK | References workspaces.id |
| relative_path | TEXT | Path from workspace root |
| file_type | TEXT | python / config / markdown / image / binary / directory |
| depth | INTEGER | Directory depth from root |
| size_bytes | INTEGER | File size |
| file_last_modified | DATETIME | Filesystem modification timestamp |
| last_scanned | DATETIME | When the agent last read this file |
| content_hash | TEXT | SHA-256 for change detection |
| embedding | BLOB | Vector from file contents or summary |
| summary | TEXT | Agent's compressed understanding of the file |

### 4.4 Operational Support

#### 4.4.1 sessions

Groups short-term memory entries by interaction session. Session summaries become prime candidates for midterm promotion.

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| started_at | DATETIME | Session start |
| ended_at | DATETIME | Session end |
| summary | TEXT | Generated summary at session close |
| embedding | BLOB | Vector of the summary |
| status | TEXT | active / closed |
| workspace_id | TEXT FK | Optional: associated workspace |

#### 4.4.2 meta_config

Agent-level settings stored inside the database for full portability. The database carries its own operating parameters.

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| key | TEXT UNIQUE | Setting name (e.g., decay_rate_multiplier, embedding_model, llm_provider, llm_api_key, llm_model, markdown_inbox_path, markdown_watch_enabled) |
| value | TEXT | Setting value |
| updated_at | DATETIME | Last modification timestamp |

#### 4.4.3 contradictions

Structured log of conflicts between memories and their resolution outcomes. Critical for domains where acting on contradicted knowledge has real consequences.

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| memory_a_id | TEXT | First conflicting memory ID |
| memory_a_table | TEXT | Table of first memory |
| memory_b_id | TEXT | Second conflicting memory ID |
| memory_b_table | TEXT | Table of second memory |
| resolution | TEXT | a_kept / b_kept / both_revised / merged / unresolved |
| reasoning | TEXT | Why the resolution was chosen |
| resolved_at | DATETIME | When resolved |
| resolved_by | TEXT | agent / user |

#### 4.4.4 audit_log

Immutable forensic record of every write operation across all tables. Enables rollback capability and behavioral diagnostics.

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| timestamp | DATETIME | When the operation occurred |
| table_name | TEXT | Affected table |
| row_id | TEXT | Affected row ID |
| operation | TEXT | insert / update / delete / promote / demote |
| before_snapshot | JSON | Row state before change (optional for inserts) |
| after_snapshot | JSON | Row state after change |
| triggered_by | TEXT | consolidation / user_feedback / agent_inference / migration / markdown_import / manual |

#### 4.4.5 feedback

User corrections, endorsements, and annotations on any memory or skill. Processed by the next consolidation cycle.

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| target_id | TEXT | ID of the record being annotated |
| target_table | TEXT | Table of the target record |
| feedback_type | TEXT | correction / endorsement / annotation / deletion_request |
| content | TEXT | The feedback text |
| created_at | DATETIME | When the feedback was submitted |
| processed | BOOLEAN | Whether the consolidation cycle has picked this up |

#### 4.4.6 context_snapshots

Captures the exact knowledge state used when the agent makes a decision. Reproducibility and diagnostic layer.

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| timestamp | DATETIME | When the snapshot was taken |
| trigger_description | TEXT | What prompted the decision |
| memory_ids | JSON | Array of {id, table} objects for memories in context |
| skill_ids | JSON | Array of skill IDs in play |
| relation_ids | JSON | Array of relation IDs traversed |
| goal_id | TEXT FK | Optional: driving goal |
| outcome | TEXT | Optional: what the agent did with this context |

#### 4.4.7 notification_queue

Proactive alerts generated when incoming information matches active goals or operator-defined alert conditions. Surfaced through Tauri system tray in desktop mode or webhook POST in headless mode.

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| agent_id | TEXT | Agent that generated the notification |
| trigger_type | TEXT | goal_match / alert_condition / contradiction_detected / consolidation_complete |
| title | TEXT | Short notification title |
| body | TEXT | Notification detail text |
| priority | TEXT | low / medium / high / critical |
| related_ids | JSON | Array of {id, table} objects for the records that triggered this notification |
| created_at | DATETIME | When the notification was generated |
| read | BOOLEAN | Whether the operator has acknowledged this notification |
| delivered | BOOLEAN | Whether the notification was successfully delivered (tray or webhook) |

### 4.5 Performance Optimization

#### 4.5.1 views

Named graph projections for mind-map visualization. Saves center node, traversal depth, filter criteria, and layout preferences.

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| name | TEXT | View name |
| center_node_id | TEXT | Focal point record ID |
| center_node_table | TEXT | Focal point table |
| depth_limit | INTEGER | Degrees of graph traversal from center |
| filters | JSON | Min edge weight, allowed edge types, time range, confidence threshold |
| layout_hints | JSON | Color coding, grouping, collapsed branches |

#### 4.5.2 embeddings_cache

Precomputed similarity scores between frequently co-retrieved entries. Avoids redundant vector math on constrained hardware.

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| node_a_id | TEXT | First node ID |
| node_a_table | TEXT | First node table |
| node_b_id | TEXT | Second node ID |
| node_b_table | TEXT | Second node table |
| similarity_score | REAL | Cosine similarity |
| computed_at | DATETIME | For cache invalidation |

---

## 5. Trigger-Based Referential Integrity

Because SQLite cannot enforce foreign keys dynamically based on a string column (polymorphic associations), referential integrity for the relations, tag_assignments, and feedback tables is enforced through SQLite triggers. This keeps all integrity logic inside the database file rather than in application code.

### 5.1 Insert Validation Triggers

BEFORE INSERT triggers on the relations table validate that both source_id and target_id exist in their respective source_table and target_table. The trigger performs a SELECT against the appropriate table using a CASE statement and raises an error via SELECT RAISE(ABORT, ...) if the referenced row does not exist. Identical triggers apply to tag_assignments and feedback.

### 5.2 Cascade Delete Triggers

AFTER DELETE triggers on every content table (short_term_memory, midterm_memory, long_term_memory, skills, skill_implementations, entities, goals, workspaces, workspace_files, sessions) clean up associated rows in relations (where source or target matches the deleted row), tag_assignments, feedback, and context_snapshots. The skills table cascade also removes all associated skill_implementations rows.

### 5.3 Periodic Integrity Check

A scheduled Python job scans all polymorphic reference columns for orphaned IDs that may have survived edge cases (e.g., triggers temporarily disabled during bulk operations). Orphans are logged to the audit_log and either cleaned automatically or flagged for user review depending on the meta_config setting for orphan_handling_mode.

---

## 6. Agent Communication Layer

The agent communication layer is the interface through which external AI systems interact with AgentDB. It is distinct from the operator-facing management API. The primary interface is MCP (Model Context Protocol), the emerging standard for agent-tool communication. A traditional REST API is also available for systems that prefer direct HTTP integration.

### 6.1 MCP Server

AgentDB runs an MCP server that exposes memory operations as standard MCP tools. Any MCP-compatible agent framework (Claude Code, OpenClaw, Letta, LangChain agents, custom implementations) can connect to AgentDB by pointing their MCP client at the server URL. No custom adapter code is required on the agent side.

The MCP server exposes the following tools: agentdb_context (retrieve ranked memories, goals, skills, and entity context for a query), agentdb_ingest (store an observation in short-term memory), agentdb_ingest_batch (bulk store multiple observations), agentdb_skill_match (find applicable skills by semantic similarity), agentdb_skill_execute (execute a skill and log the result), agentdb_goals_check (match incoming context against active goals), agentdb_identity (retrieve all identity and directive memories), agentdb_session_start (create a new session), and agentdb_session_end (close a session and trigger summary generation).

Each MCP tool call includes an agent_id parameter that scopes the operation to a specific agent. This enables multi-agent setups where each agent maintains its own memory while sharing access to organizational knowledge marked with agent_id "shared." The MCP server validates agent_id against the agents table and rejects requests from unregistered agents.

### 6.2 REST Agent API

For systems that do not support MCP, the same operations are available as JSON REST endpoints under the /api/agent namespace. Authentication is handled via a locally-stored API key configured in meta_config. All REST endpoints accept an agent_id parameter with identical scoping behavior to the MCP interface.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/agent/context | Primary retrieval endpoint. Accepts a query string, agent_id, and optional filters (tier, entity, tags, time range, confidence threshold). Returns ranked memories using multi-strategy retrieval. |
| POST | /api/agent/ingest | Stores a new observation in short_term_memory scoped to the specified agent_id. |
| POST | /api/agent/ingest/batch | Bulk ingestion for storing multiple observations within the same session. |
| POST | /api/agent/skill/match | Accepts a task description and returns ranked skills by semantic similarity. |
| POST | /api/agent/skill/execute | Triggers execution of a specific skill by ID against provided inputs. |
| POST | /api/agent/goals/check | Accepts incoming context and returns any active goals whose embeddings match above threshold. |
| GET | /api/agent/identity | Returns all long_term_memory entries with category set to "identity" or "directive." |
| POST | /api/agent/session/start | Creates a new session row and returns the session_id. |
| POST | /api/agent/session/end | Closes a session. Triggers summary generation and embedding. |
| GET | /api/agent/health | System status including database connectivity, sidecar uptime, embedding model availability, encryption status, and last consolidation timestamp. |

### 6.3 Multi-Strategy Retrieval Pipeline

When any agent calls the context retrieval operation (via MCP or REST), the backend executes a multi-strategy retrieval pipeline that combines four complementary search methods to maximize recall accuracy.

First, semantic vector search generates an embedding from the query text and performs cosine similarity search across all three memory tiers, returning the top N results per tier (configurable in meta_config). This catches memories that are conceptually related even when phrasing differs.

Second, BM25 keyword search runs the query against SQLite FTS5 full-text indexes on all memory content columns. This catches memories that share exact terms or rare keywords that vector similarity might not weight heavily enough.

Third, graph traversal identifies entities mentioned in the query, looks them up in the entities table, and walks the relations graph to pull connected memories, skills, and other entities within a configurable hop depth. This catches memories that are structurally related through the knowledge graph even if they are neither semantically nor lexically similar to the query.

Fourth, temporal weighting applies a recency boost to results based on their creation or last-accessed timestamps. Recent memories receive higher scores, configurable via a decay curve parameter in meta_config. This ensures the agent's context reflects current state rather than stale history.

The results from all four strategies are deduplicated, merged, and passed through a cross-encoder reranker (e.g., cross-encoder/ms-marco-MiniLM-L-6-v2, runs locally) that scores each candidate against the original query for final ranking. The top results are assembled into the context payload along with matched goals, applicable skills, and expanded entity context.

### 6.4 Multi-Agent Memory Scoping

When multiple agents share a single AgentDB instance, memory access is scoped by agent_id. Each agent sees its own memories by default. Memories with agent_id set to "shared" are visible to all agents. The operator controls which memories are shared through the UI or markdown authoring frontmatter.

Cross-agent memory queries are supported through an explicit parameter (include_agents) that specifies which other agents' memories to include in the retrieval. This enables patterns like a research agent sharing findings with an operations agent, or a code agent accessing architectural decisions made during conversations with a different agent. The operator retains full visibility across all agents through the management UI regardless of scoping.

The agents table stores per-agent configuration overrides including custom retrieval preferences (e.g., a code agent might weight keyword search higher than a conversational agent), context size limits, and provider settings. This allows each agent to be tuned for its specific role without affecting others.

### 6.5 Provider-Agnostic Middleware

The middleware module sits between the application and whatever LLM provider is configured. It implements a standard interface: receive a user message, query AgentDB for context, construct a provider-specific API request with the context injected (typically as a system prompt prefix or structured context block), send the request to the provider, receive the response, ingest both the user message and the AI response into AgentDB, and return the response to the caller.

Provider adapters are implemented as pluggable Python modules, one per provider. Each adapter knows how to format AgentDB context for its provider's API. The Claude adapter structures context as XML-tagged blocks in the system prompt. The OpenAI adapter uses the system message. A local LLM adapter passes context as a prompt prefix. The adapter interface is simple: format_context(context_payload) returns a provider-ready string, and call_provider(messages, formatted_context) returns the AI response. Adding a new provider means writing one adapter module with those two methods.

The provider is configured in meta_config with keys for llm_provider (claude, openai, local, custom), llm_api_key (encrypted at rest), llm_model (the specific model identifier), and llm_endpoint (for local or custom providers). Switching providers is a config change, not a code change.

### 6.6 Context Snapshot on Every Exchange

Every conversation exchange that passes through the middleware automatically creates a context_snapshot row. This captures exactly which memories, skills, goals, and relations were used to inform that specific response, including which retrieval strategies contributed each result. The snapshot is linked to the session and includes the outcome (the AI's response summary). This gives the operator complete forensic visibility into why the agent said what it said.

---

## 7. Markdown Authoring Layer

The markdown authoring layer enables the operator to directly create, edit, and inject knowledge into the agent's memory system using markdown as the authoring format. This provides a human-friendly, version-controllable alternative to raw database manipulation for shaping what the agent knows and how it behaves.

### 7.1 Document Types

The system recognizes four markdown document types, each routing to different database tables and processing pipelines based on YAML frontmatter metadata.

**Memory documents** are direct knowledge injections. The markdown body becomes a long_term_memory entry with confidence set to 1.0 and provenance set to "user_authored." These bypass the short-term to midterm to long-term promotion pipeline entirely because the human operator is explicitly asserting the knowledge as ground truth. Memories can be categorized as fact, relationship, preference, or procedure through the frontmatter.

**Instruction documents** are behavioral directives that shape the agent's personality, constraints, and response patterns. The markdown body becomes a long_term_memory entry with category set to "directive." These are retrieved by the /api/agent/identity endpoint and injected into every conversation exchange. Instructions define rules like "always respond in a direct, no-fluff style," "never recommend cloud-dependent solutions," or "when discussing real estate, prioritize cash flow over appreciation." The operator programs the agent's behavior through natural language rather than code.

**Skill documents** define new agent capabilities. The markdown structure maps to both the skills table and the skill_implementations table. The document title becomes the skill name. A description section becomes the skill description and generates the semantic matching embedding. A metadata section (language, dependencies, execution_type, input_schema, output_schema) populates the skills table fields. Fenced code blocks become skill_implementations rows with the language tag determining the implementation language. Multiple code blocks in a single document create a composite skill with execution_order derived from block sequence.

**Knowledge documents** are long-form reference material: SOPs, product documentation, technical references, domain knowledge. These are chunked into multiple long_term_memory entries because a single embedding cannot meaningfully represent a multi-page document. The chunking strategy splits on markdown headings (h2 and h3) with each section becoming its own memory entry. All chunks are linked to a parent entity representing the document through relations with edge_type "chunk_of." The parent entity is created in the entities table with entity_type "document." This preserves the document's structure in the knowledge graph while making each section independently retrievable by semantic search.

### 7.2 Frontmatter Schema

Every markdown document processed by the authoring layer must include YAML frontmatter specifying at minimum the document type. Additional fields depend on the type.

```yaml
# Memory document
---
type: memory
category: fact
tags: [hardware, vendor, pricing]
entities: [Orgill, Whitten Hardware]
---

# Instruction document
---
type: instruction
priority: high
tags: [behavior, communication-style]
---

# Skill document
---
type: skill
execution_type: code_procedure
language: python
dependencies: [requests, json]
input_schema: {"url": "string", "params": "object"}
output_schema: {"status": "integer", "data": "object"}
---

# Knowledge document
---
type: knowledge
title: Whitten Hardware Vendor SOP
tags: [sop, operations, whitten]
entities: [Whitten Hardware, Orgill, True Value]
---
```

### 7.3 Processing Pipeline

When a markdown document is submitted (via the UI editor or the file watcher), the backend executes the following pipeline. First, it parses the YAML frontmatter and validates required fields based on document type. Second, it extracts the markdown body and processes it according to type (single entry for memory/instruction, structured extraction for skill, chunking for knowledge). Third, it generates embeddings for all content that will be stored. Fourth, it creates the appropriate database rows (long_term_memory, skills, skill_implementations, entities). Fifth, it creates relations between the new entries and any entities specified in the frontmatter or extracted from the content. Sixth, it creates tag_assignments for any tags specified in the frontmatter. Seventh, it logs all operations to the audit_log with triggered_by set to "markdown_import." Eighth, it returns a summary of what was created.

If the markdown document has the same title as an existing entry (matched by embedding similarity above 0.95 on the title/name), the system treats it as an update rather than a new entry. The existing record is modified, a new skill_implementations version is created if applicable, and the audit_log captures the before/after state. This enables iterative refinement of knowledge and skills without creating duplicates.

### 7.4 Built-In Markdown Editor

The UI includes a markdown editor view accessible from the main navigation. The editor provides a textarea with monospace font for writing markdown, a live preview panel showing the rendered output, a type selector dropdown (memory, instruction, skill, knowledge) that pre-populates the YAML frontmatter template, optional metadata fields that surface dynamically based on the selected type (category, priority, tags, entities, language, dependencies, schemas), and a submit button that sends the document to the processing pipeline and displays the creation summary.

The editor also supports loading existing memories, instructions, or skills back into the editor for modification. The operator selects a record from the memory browser or skills manager, clicks "Edit as Markdown," and the system reverse-generates a markdown document from the database record, complete with frontmatter. After editing, resubmission updates the existing record through the deduplication-aware pipeline.

### 7.5 File Watcher

The system monitors a configurable inbox directory (path set in meta_config as markdown_inbox_path, enabled/disabled via markdown_watch_enabled). When a new .md file appears in the inbox, the file watcher picks it up, validates the frontmatter, processes it through the standard pipeline, and moves the file to a processed subdirectory with a timestamp prefix. If processing fails (invalid frontmatter, missing required fields, embedding generation error), the file is moved to a failed subdirectory with an error log file alongside it.

The file watcher enables several powerful workflows. The operator can author markdown in any external editor (VS Code, Vim, whatever they prefer) and drop files into the inbox. A CI/CD pipeline can push markdown files to the inbox after merging a pull request, enabling git-managed agent knowledge. Batch loading of reference material is as simple as copying a folder of markdown files into the inbox directory.

In Tauri mode, the file watcher runs as part of the Python sidecar. In headless mode, it runs as a background thread in the Python process. The watcher uses polling (configurable interval in meta_config) rather than OS-level filesystem events for maximum portability across platforms.

### 7.6 Version-Controlled Knowledge

Because the authoring layer accepts standard markdown files with YAML frontmatter, the operator can maintain their agent's knowledge base in a git repository. The repository contains directories for each document type (memories/, instructions/, skills/, knowledge/), and the operator edits files using standard git workflows: branch, edit, commit, review, merge. A post-merge hook or manual copy pushes changed files to the file watcher inbox for processing.

This gives the operator full version history, diff capability, branching for experimental knowledge changes, and rollback through git revert rather than database manipulation. The database remains the runtime source of truth, but the git repository serves as the authoring source of truth. If the database is lost or corrupted, the entire knowledge base can be rebuilt by re-processing all markdown files from the repository through the inbox pipeline.

---

## 8. Sleep-Time Asynchronous Memory Processing

The sleep-time processing system runs during periods when no active conversation is in progress. Unlike the consolidation engine which handles mechanical promotion, decay, and pruning, sleep-time processing performs higher-order cognitive operations on the knowledge base: reflection, pattern recognition, proactive goal monitoring, and notification generation.

### 8.1 Idle Detection

The system tracks the timestamp of the last agent API call. When the idle period exceeds a configurable threshold (sleep_idle_threshold_seconds in meta_config, default 300 seconds), the sleep-time processor activates. It deactivates immediately when a new agent API call arrives, ensuring zero interference with active conversations. In Tauri mode, the system tray icon indicates when sleep-time processing is active.

### 8.2 Reflection Cycles

During sleep-time, the processor runs reflection cycles that analyze recent sessions for patterns the real-time consolidation engine might miss. It examines clusters of midterm memories across multiple sessions to identify recurring themes that haven't yet been promoted to long-term. It evaluates whether existing long-term memories are still consistent with recent evidence and flags stale entries for revalidation. It identifies entities that frequently co-occur across sessions but lack explicit relations, and proposes new edges for the knowledge graph. Proposed changes are logged to the audit_log and, depending on the confidence level, either applied automatically or queued for operator review via the feedback table.

### 8.3 Graph Strengthening and Pruning

The sleep-time processor analyzes the relations graph for structural health. Relations that are frequently traversed during context retrieval have their weights increased. Relations that have never been traversed since creation and are older than a configurable threshold have their weights decreased. The processor identifies disconnected subgraphs (clusters of memories with no relational path to the rest of the knowledge base) and flags them for operator review, since isolated knowledge clusters may indicate either incomplete graph construction or irrelevant memories that should be pruned.

### 8.4 Proactive Goal Monitoring and Notifications

The processor scans all memories ingested since the last sleep cycle against active goal embeddings. If any new memory matches a goal above the configured similarity threshold, a notification is generated in the notification_queue table. The notification includes the matched goal, the triggering memory, and the similarity score. In Tauri mode, high-priority notifications are surfaced through the system tray. In headless mode, notifications are delivered via a configurable webhook URL (notification_webhook_url in meta_config).

The operator can also define custom alert conditions stored in meta_config as JSON rules. Examples include: alert when any memory is ingested containing a specific entity, alert when a contradiction is detected involving long-term memories above a confidence threshold, alert when the database file exceeds a size threshold. The sleep-time processor evaluates these conditions on each cycle.

### 8.5 Pre-Computation

During sleep periods, the processor pre-computes and caches results that are likely to be needed in future conversations. It identifies the operator's most frequently queried entities and topics (based on context_snapshot history), generates fresh context payloads for those topics, and stores the results in the embeddings_cache. This reduces first-query latency when the operator returns to a familiar topic after a break.

## 9. Consolidation Engine

### 9.1 Short-to-Midterm Consolidation

Runs on the interval defined in meta_config (consolidation_interval_seconds). Scans short_term_memory for entries with status "active" whose TTL has not expired. Groups semantically similar entries using embedding cosine similarity with a configurable threshold. Generates consolidated midterm entries from each cluster, preserving source_ids for provenance. Extracts named entities and populates the entities table and entity_ids field. Sets initial confidence based on cluster size and source diversity. Updates short_term_memory status to "promoted" for consumed entries.

### 9.2 Midterm-to-Long-Term Promotion

Evaluates midterm entries whose confidence exceeds the promotion threshold defined in meta_config. Checks for contradictions against existing long-term memories using embedding similarity followed by content analysis. If no contradiction exists, promotes the entry. If a contradiction is found, logs it in the contradictions table with resolution set to "unresolved" and flags both entries for user review via the feedback table.

### 9.3 Decay and Pruning

Midterm entries whose decay_weight reaches zero are archived or deleted based on meta_config settings. Long-term entries whose last_validated timestamp exceeds a configurable staleness threshold are flagged for revalidation. The agent can revalidate automatically if it encounters corroborating or contradicting evidence, or flag for user review. User-authored entries (provenance = "user_authored") are exempt from automatic decay and pruning; only explicit user action can remove them.

### 9.4 Feedback Processing

Each consolidation cycle checks the feedback table for unprocessed entries. Endorsements increase the target memory's confidence score. Corrections trigger a contradiction resolution flow. Deletion requests queue the target for removal after confirmation. Annotations are attached as relations with edge_type "annotated_by." All processed feedback entries are marked with processed = true.

---

## 10. External Chat Migration Pipeline

The migration system converts exported chat histories from external LLM providers into structured agent knowledge. The pipeline is a batch process invoked via the Import Manager in the UI or via Python CLI.

### 10.1 Supported Providers

| Provider | Export Format |
|----------|--------------|
| ChatGPT | conversations.json from Settings > Data Controls > Export Data (ZIP) |
| Claude | Export format from Settings > Account > Export Data |
| Generic | JSONL with {role, content, timestamp} per line for custom providers |

### 10.2 Phase 1: Raw Ingestion

The parser reads the provider-specific export format and linearizes each conversation. ChatGPT conversations are tree-structured due to edit branching; the parser walks the parent chain from leaf to root and selects the canonical path (last branch taken). Each conversation becomes a sessions row with original timestamps preserved. Each message becomes a short_term_memory row with source set to the provider identifier (e.g., "chatgpt_import"), status set to "imported," and an embedding generated from the message content.

### 10.3 Phase 2: Consolidation

The standard consolidation engine runs against imported entries. The agent scans each session, identifies key topics, decisions, facts, preferences, and instructions. These become midterm_memory entries with moderate initial confidence scores since they originate from a foreign system. Entity extraction populates the entities table.

### 10.4 Phase 3: Promotion

A second pass identifies patterns that repeat across multiple imported sessions. Preferences or facts appearing in many conversations receive high confidence and are promoted to long_term_memory. Single-occurrence items remain in midterm with higher decay weight. Contradictions across sessions are logged in the contradictions table with resolution set to "unresolved."

### 10.5 Phase 4: Graph Construction

The relations table is populated with edges linking entities to the memories where they appeared, memories to their source sessions, co-occurring entities to each other, and any extracted skills or procedures to their discussion contexts. This phase builds the initial mind-map topology from the imported data.

### 10.6 Phase 5: User Review

The feedback table is seeded with entries flagged for review: low-confidence promotions, unresolved contradictions, entities with conflicting attributes, and any content the pipeline was uncertain about. A summary report is generated showing total conversations imported, memories created per tier, entities extracted, contradictions found, and items pending review.

### 10.7 Deduplication

If the operator imports from multiple providers, the pipeline runs cross-import deduplication using embedding similarity on midterm entries. Overlapping memories are either merged with boosted confidence or flagged for review if details diverge.

---

## 11. User Interface

The UI is a single-file HTML application with inline CSS and vanilla ES6 JavaScript, served through Tauri's native webview in desktop mode or via the Python HTTP server in headless mode. No frameworks, no build tools, no external CDN dependencies.

### 11.1 Dashboard

Landing page showing aggregate statistics: total memories per tier (filterable by agent), total entities, active goals, unresolved contradictions, pending feedback items, unread notifications, last consolidation timestamp, last sleep-time cycle timestamp, database file size, encryption status, embedding model info, configured LLM provider, sidecar health status, file watcher status (enabled/disabled, inbox path, files pending), and an agent selector dropdown that scopes the entire UI to a specific agent or shows all agents combined.

### 11.2 Memory Browser

Tabbed interface for short-term, midterm, and long-term memory tables. Each tab provides sortable columns, text search, semantic search (enter a query, backend returns ranked results by embedding similarity), and filters for confidence, decay weight, category, date range, entity, tags, provenance source, and agent_id. Clicking a memory row expands it to show full content, provenance chain, linked entities, related memories via the relations table, which retrieval strategies have surfaced this memory in past queries, and any feedback history. An "Edit as Markdown" button opens the record in the markdown editor for modification.

### 11.3 Mind Map / Knowledge Graph

Radial graph visualization centered on a user-selected node. Renders first-degree relations as main branches, second-degree as sub-branches, with edge weight controlling line thickness and confidence controlling node opacity. Nodes are color-coded by source table. The operator can click any node to re-center the graph, expand or collapse branches, filter by edge type or confidence threshold, and save the current view to the views table. Knowledge document chunks appear as clustered nodes connected to their parent document entity. Implemented using Canvas 2D or a lightweight JS graph library embedded inline.

### 11.4 Chat Console

Built-in conversational interface that routes messages through the full memory-augmented pipeline. The chat console is split into two panels. The left panel is the conversation thread showing user messages and AI responses in a standard chat layout. The right panel is the observability sidebar, which updates on every exchange to show the exact context that was retrieved and injected.

The observability sidebar displays: the memories retrieved by the context endpoint, ranked by similarity score and color-coded by tier (short-term, midterm, long-term); any active goals that matched the current query; skills that were considered applicable; entities that were identified and expanded; and the full context payload that was sent to the LLM provider. After the AI responds, the sidebar also shows what was ingested back into short-term memory from the exchange.

The chat console supports provider switching via a dropdown that reads from meta_config. Changing the provider mid-conversation is allowed; the session continues and the memory system treats it as a continuous interaction regardless of which LLM is responding. A "raw mode" toggle shows the actual API request and response payloads for debugging.

The chat console is an observability and testing tool. It is not intended to replace a provider's native chat interface for daily use, though it can serve that purpose if the operator prefers having full memory transparency on every exchange.

### 11.5 Markdown Editor

Dedicated authoring interface for creating and editing markdown documents that inject knowledge into the agent's memory. The editor provides a split-pane layout with a monospace textarea on the left and a rendered markdown preview on the right. A type selector dropdown (memory, instruction, skill, knowledge) pre-populates the YAML frontmatter template. Dynamic metadata fields surface below the type selector based on the selected type: category and entity pickers for memories, priority selector for instructions, language/dependency/schema fields for skills, and title/entity pickers for knowledge documents.

The submit button sends the document through the processing pipeline and displays a creation summary showing what records were created, what entities were linked, and what tags were applied. An "Edit Existing" mode loads records from the memory browser or skills manager back into the editor as reverse-generated markdown for modification.

The editor also provides a batch import interface: select multiple .md files via the file picker (native dialog in Tauri mode) and process them sequentially through the pipeline with a progress indicator and summary report on completion.

### 11.6 Skills Manager

List view of all skills with name, execution type, use count, success rate, and last used date. Expanding a skill shows its description, input/output schemas, version history with all implementations from skill_implementations, dependency lists per version, and a list of domains where it has been applied. The operator can edit descriptions, archive skills, view or rollback to previous implementation versions, manually create new skills, and open any skill in the markdown editor for structured editing.

### 11.7 Feedback and Contradictions

Dedicated views for unresolved contradictions and pending feedback items. Contradictions show both conflicting memories side by side with a resolution interface (keep A, keep B, merge, revise both). Feedback items show the target memory with the feedback content and action buttons (apply correction, accept endorsement, execute deletion, dismiss).

### 11.8 Import Manager

File upload interface for external chat exports. In Tauri mode, uses native file picker dialog. Provider selection dropdown. Progress bar showing pipeline phase (ingestion, consolidation, promotion, graph construction, review). Summary report display on completion. Direct link to the feedback view for reviewing flagged items.

### 11.9 Audit Log Viewer

Chronological log of all database operations with filters for table, operation type, trigger source (including "markdown_import"), and date range. Expanding a row shows before/after snapshots as a diff view. Context snapshot entries link directly to the chat console exchange that produced them.

### 11.10 Notifications

Chronological list of all proactive notifications generated by the sleep-time processor and goal monitoring system. Each notification shows the trigger type, priority, title, body, and links to the related records that caused it. The operator can mark notifications as read, dismiss them, or click through to the relevant memory, goal, or contradiction in the appropriate view. A notification badge on the Tauri system tray and the UI navigation bar shows the count of unread high-priority notifications. Filter controls allow viewing by trigger type, priority, agent, and date range.

### 11.11 Settings

Editor for all meta_config values including memory behavior settings (decay rates, promotion thresholds, TTL defaults, consolidation interval), LLM provider configuration (provider, API key, model, endpoint), multi-agent management (register new agents, edit agent configs, view agent activity), sleep-time processing settings (idle threshold, reflection cycle interval, graph pruning thresholds, pre-computation preferences), notification settings (webhook URL for headless mode, priority thresholds for system tray alerts, custom alert condition rules), encryption settings (enable/disable SQLCipher encryption, change encryption passphrase), and markdown authoring settings (inbox path, file watcher enabled/disabled, polling interval). API key and encryption passphrase fields are masked by default with a reveal toggle. Includes a database maintenance section with buttons for manual consolidation trigger, manual sleep-time cycle trigger, integrity check, embedding cache rebuild, and database export/backup. In Tauri mode, includes database file path management and sidecar process controls.

---

## 12. API Endpoints

The Python backend exposes three interfaces. The operator API (/api/) serves the management UI via REST. The agent API (/api/agent/) serves external AI systems via REST. The MCP server exposes the same agent operations as MCP tools for any MCP-compatible client. All REST responses follow a consistent {status, data, error} envelope.

### 12.1 Operator API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/stats | Dashboard aggregate statistics, filterable by agent_id |
| GET | /api/memories/{tier} | List memories with pagination, filters, sort, and agent_id scoping |
| GET | /api/memories/{tier}/{id} | Single memory with full relations and provenance |
| POST | /api/memories/search | Multi-strategy semantic search across all tiers |
| POST | /api/feedback | Submit feedback on a memory or skill |
| GET | /api/entities | List all entities with filters |
| GET | /api/entities/{id}/graph | Subgraph centered on entity to specified depth |
| GET | /api/skills | List all skills with stats |
| GET | /api/skills/{id}/implementations | All implementation versions for a skill |
| PUT | /api/skills/{id} | Update skill description or archive |
| POST | /api/skills/{id}/rollback/{version} | Rollback skill to a previous implementation |
| GET | /api/goals | List goals with status filter |
| POST | /api/goals | Create a new goal |
| GET | /api/relations/{node_id} | All relations for a given node |
| GET | /api/contradictions | List unresolved contradictions |
| POST | /api/contradictions/{id}/resolve | Submit resolution for a contradiction |
| GET | /api/audit | Paginated audit log with filters |
| POST | /api/import | Start migration pipeline (multipart file upload) |
| GET | /api/import/status | Pipeline progress for active import |
| GET | /api/config | All meta_config values |
| PUT | /api/config/{key} | Update a config value |
| GET | /api/agents | List all registered agents with activity stats |
| POST | /api/agents | Register a new agent |
| PUT | /api/agents/{id} | Update agent config |
| GET | /api/notifications | List notifications with filters (read/unread, priority, agent, trigger type) |
| PUT | /api/notifications/{id}/read | Mark a notification as read |
| POST | /api/notifications/dismiss | Batch dismiss notifications |
| POST | /api/maintenance/consolidate | Trigger manual consolidation |
| POST | /api/maintenance/sleep-cycle | Trigger manual sleep-time processing cycle |
| POST | /api/maintenance/integrity-check | Run orphan detection scan |
| GET | /api/views | List saved graph views |
| POST | /api/views | Save a new graph view |
| GET | /api/workspaces | List registered workspaces |
| POST | /api/workspaces/scan | Trigger workspace rescan |
| POST | /api/markdown/submit | Submit a markdown document through the processing pipeline |
| POST | /api/markdown/batch | Submit multiple markdown files for sequential processing |
| GET | /api/markdown/reverse/{table}/{id} | Reverse-generate markdown from an existing database record |
| GET | /api/markdown/watcher/status | File watcher status and pending file count |

### 12.2 Agent API (REST Fallback)

The MCP server is the primary agent interface (see Section 6.1). The REST endpoints below provide identical functionality for systems that do not support MCP. All endpoints accept an agent_id parameter for multi-agent scoping.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/agent/context | Multi-strategy retrieval: ranked memories, goals, skills, and entity context |
| POST | /api/agent/ingest | Store a single observation in short_term_memory |
| POST | /api/agent/ingest/batch | Bulk ingest multiple observations |
| POST | /api/agent/skill/match | Find applicable skills by multi-strategy similarity |
| POST | /api/agent/skill/execute | Execute a skill and log the result |
| POST | /api/agent/goals/check | Match incoming context against active goal embeddings |
| GET | /api/agent/identity | Retrieve all long-term identity and directive memories |
| POST | /api/agent/session/start | Create a new session and return session_id |
| POST | /api/agent/session/end | Close a session, trigger summary generation |
| GET | /api/agent/health | System status including encryption status and sleep-time processor state |
| POST | /api/agent/chat | Full pipeline: context retrieval, LLM call via middleware, ingestion, observability payload |

---

## 13. Implementation Milestones

### Phase 1: Foundation

SQLite schema creation with all twenty-three tables including skill_implementations. Trigger implementation for polymorphic referential integrity and cascade deletes. meta_config seeded with defaults. Python data access module with CRUD operations for all tables. Embedding generation pipeline using sentence-transformers. Basic CLI for database initialization and manual operations.

### Phase 2: Agent Communication Layer and MCP

MCP server implementation exposing all agent memory operations as MCP tools. REST agent API endpoints as fallback (context retrieval, ingestion, skill matching, goal checking, identity, session management). Multi-strategy retrieval pipeline: semantic vector search, BM25 keyword search via FTS5 indexes, graph traversal, temporal weighting, and cross-encoder reranking. Multi-agent support: agents table, agent_id scoping on all memory operations, shared vs. private memory access control. Provider-agnostic middleware module with adapter interface. Claude and OpenAI adapters. Local LLM adapter. Context snapshot generation on every exchange.

### Phase 3: Consolidation Engine

Short-to-midterm consolidation with configurable clustering threshold. Midterm-to-long-term promotion with contradiction detection. Decay and pruning jobs (with user-authored entry exemption). Feedback processing loop. Scheduled execution via configurable interval.

### Phase 4: Markdown Authoring Layer

Markdown parser with YAML frontmatter validation. Processing pipeline for all four document types (memory, instruction, skill, knowledge). Knowledge document chunking on heading boundaries. Deduplication-aware update handling. Reverse markdown generation from existing records. File watcher with inbox/processed/failed directory structure.

### Phase 5: Migration Pipeline

ChatGPT export parser with tree linearization. Claude export parser. Generic JSONL parser. Five-phase pipeline implementation. Cross-provider deduplication. CLI invocation with summary report output.

### Phase 6: User Interface

Python HTTP server with operator API, agent REST API, and MCP server. Single-file HTML/CSS/JS application. Dashboard with agent selector and notification bell, memory browser with "Edit as Markdown" integration and agent_id filtering, mind map visualization, chat console with observability sidebar showing retrieval strategy breakdown, markdown editor with type-aware frontmatter templates and batch import, skills manager with implementation version history, feedback/contradiction resolution views, import manager, notifications view with filtering and dismissal, audit log viewer, and settings editor with agent management, notification configuration, and encryption controls.

### Phase 7: Tauri Packaging

Tauri project setup with Python sidecar configuration. Sidecar lifecycle management (spawn, health monitoring, restart, graceful shutdown). Native file dialogs for imports, markdown files, and database management. System tray integration for background operation and proactive notification delivery. Build pipeline producing distributable executables for Windows, macOS, and Linux.

### Phase 8: Workspace Awareness

Workspace registration and scanning. File-level embedding and summarization. Workspace relations (imports, configures, tests, documents edges). Integration with memory system via main relations table.

### Phase 9: Sleep-Time Processing and Notifications

Sleep-time idle detection and activation logic. Reflection cycles for pattern recognition across sessions. Graph strengthening and pruning based on traversal frequency. Proactive goal monitoring with notification generation. Notification queue with Tauri system tray delivery (desktop) and webhook delivery (headless). Custom alert condition engine with JSON rule evaluation. Pre-computation of likely retrieval contexts based on usage history.

### Phase 10: Encryption and Hardening

SQLCipher integration for optional encryption at rest. Encryption enable/disable and passphrase management through the settings UI. Embeddings cache implementation. SQLite WAL mode tuning. Query performance profiling and index optimization (including FTS5 indexes for BM25). Cross-encoder reranker model download and caching. Periodic integrity check job. Database backup and export tooling. API key encryption at rest. Documentation.

---

## 14. Success Criteria

The database initializes from a single Python command and produces a valid, self-contained .db file with all tables, triggers, indexes, and default configuration including a default agent row in the agents table.

An MCP-compatible agent framework can connect to the AgentDB MCP server and successfully execute context retrieval, ingestion, skill matching, and goal checking operations without any custom adapter code on the agent side.

The multi-strategy retrieval pipeline (semantic + BM25 + graph traversal + temporal + cross-encoder reranking) returns a ranked context payload in under 500ms for a database containing 10,000+ memories. Multi-strategy retrieval demonstrably outperforms single-strategy vector search on queries where the user's phrasing differs significantly from stored memory content.

Multiple agents registered in the same AgentDB instance can maintain independent memory scopes, with each agent seeing only its own memories and shared organizational knowledge by default. Cross-agent queries explicitly requested via the include_agents parameter return results from the specified agents without leaking memories from unspecified agents.

The middleware successfully injects AgentDB context into Claude, OpenAI, and local LLM requests without provider-specific logic leaking outside the adapter modules.

The chat console displays the full observability payload (retrieved memories with retrieval strategy attribution, matched goals, applicable skills, ingested observations) for every exchange in real time.

Switching LLM providers via meta_config takes effect on the next chat exchange with no application restart required.

The sleep-time processor activates within 10 seconds of the idle threshold being exceeded and deactivates within 1 second of a new agent API call arriving, ensuring zero interference with active conversations.

Proactive notifications generated by goal monitoring during sleep-time cycles are delivered to the Tauri system tray within 5 seconds of generation. In headless mode, webhook notifications are POST-ed within 5 seconds.

A markdown document of any type (memory, instruction, skill, knowledge) is parsed, validated, embedded, stored, and linked within 2 seconds of submission.

A knowledge document of 50+ sections is chunked, embedded, stored as individual memories, and linked to a parent document entity with correct "chunk_of" relations in under 30 seconds.

The file watcher detects and processes new markdown files within the configured polling interval and correctly routes files to processed or failed directories.

An existing memory or skill can be reverse-generated into markdown, edited, and resubmitted as an update without creating duplicate records.

A ChatGPT export of 500+ conversations completes the full five-phase migration pipeline in under 10 minutes on commodity hardware and produces a browsable, searchable, semantically-linked knowledge base.

The UI renders the mind-map graph centered on any entity with two degrees of traversal in under 2 seconds with a database containing 10,000+ memories.

The consolidation engine correctly identifies and logs contradictions between imported memories from different providers.

User-authored memories (provenance = "user_authored") are exempt from automatic decay and pruning across all consolidation cycles.

Skill implementations can be versioned, rolled back, and dependency-checked before execution on constrained hardware.

SQLCipher encryption can be enabled on an existing unencrypted database and disabled on an encrypted database through the settings UI without data loss. An encrypted .db file is unreadable without the passphrase.

The Tauri executable launches, spawns the Python sidecar, and serves the full UI within 5 seconds on commodity hardware.

The entire system runs offline with zero external API calls after initial embedding and reranker model download (LLM provider calls excluded when using cloud-hosted models).

The .db file can be copied to a fresh machine and operate immediately in headless mode with only Python and the embedding model installed.

The same .db file works identically in both Tauri desktop mode and headless mode with no modification.

A git repository of markdown files can be batch-imported through the file watcher inbox to fully reconstruct an agent's knowledge base from scratch.
