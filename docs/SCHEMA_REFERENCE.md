# AgentDB Schema Reference

Complete field-level reference for all database tables. Current as of v1.6 implementation.

---

## Memory Tables

### short_term_memory

The agent's immediate working context. High write frequency, aggressive pruning via TTL.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| agent_id | TEXT | NOT NULL, DEFAULT 'default' | Scoping for multi-agent setups |
| timestamp | DATETIME | NOT NULL, DEFAULT now | Creation time |
| source | TEXT | NOT NULL, CHECK IN (conversation, tool_output, sensor, chatgpt_import, claude_import, markdown_authored) | Input channel |
| content | TEXT | NOT NULL | Raw observation text |
| embedding | BLOB | | 384-dim float32 vector |
| ttl_seconds | INTEGER | NOT NULL, DEFAULT 3600 | Time-to-live before expiration |
| session_id | TEXT | FK → sessions.id | Groups entries by conversation |
| status | TEXT | NOT NULL, DEFAULT 'active', CHECK IN (active, promoted, expired, imported) | Lifecycle state |

### midterm_memory

Consolidated observations. Subject to confidence-based promotion and time-based decay.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| agent_id | TEXT | NOT NULL, DEFAULT 'default' | Multi-agent scoping |
| created_at | DATETIME | NOT NULL, DEFAULT now | Consolidation timestamp |
| last_accessed | DATETIME | NOT NULL, DEFAULT now | Used for decay calculations |
| content | TEXT | NOT NULL | Consolidated text |
| embedding | BLOB | | 384-dim float32 vector |
| confidence | REAL | NOT NULL, DEFAULT 0.5, CHECK 0.0–1.0 | Reinforcement-based score |
| source_ids | JSON | | Array of STM IDs this was consolidated from |
| entity_ids | JSON | | Array of extracted entity IDs |
| decay_weight | REAL | NOT NULL, DEFAULT 1.0 | Decreases over time unless accessed |
| category | TEXT | NOT NULL, DEFAULT 'observation', CHECK IN (observation, pattern, inference) | Classification |

### long_term_memory

Bedrock knowledge. High confidence threshold for entry. Periodic revalidation.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| agent_id | TEXT | NOT NULL, DEFAULT 'default' | "shared" for organizational knowledge |
| created_at | DATETIME | NOT NULL, DEFAULT now | Commit timestamp |
| last_validated | DATETIME | NOT NULL, DEFAULT now | Last confirmation of accuracy |
| content | TEXT | NOT NULL | Knowledge text |
| embedding | BLOB | | 384-dim float32 vector |
| confidence | REAL | NOT NULL, DEFAULT 0.9, CHECK 0.0–1.0 | Should be >0.8 |
| provenance | JSON | | Source chain or "user_authored" / "markdown_import" |
| entity_ids | JSON | | Referenced entity IDs |
| category | TEXT | NOT NULL, DEFAULT 'fact', CHECK IN (fact, relationship, preference, procedure, identity, directive) | Knowledge type |

---

## Knowledge Infrastructure

### agents

Registry of all agents using this AgentDB instance.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | Agent identifier (e.g., "default", "email-agent") |
| name | TEXT | NOT NULL | Human-readable name |
| description | TEXT | | What this agent does |
| created_at | DATETIME | NOT NULL, DEFAULT now | Registration timestamp |
| last_active | DATETIME | | Last API call timestamp |
| config | JSON | | Per-agent overrides (retrieval prefs, context limits) |

### skills

Domain-agnostic capability definitions. Discovered by semantic similarity at inference time.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| name | TEXT | NOT NULL | Skill name |
| description | TEXT | NOT NULL | What it does (used for semantic matching) |
| embedding | BLOB | | Vector from description |
| input_schema | JSON | | Expected input structure |
| output_schema | JSON | | Expected output structure |
| version | INTEGER | NOT NULL, DEFAULT 1 | Current version number |
| created_at | DATETIME | NOT NULL, DEFAULT now | First registered |
| last_used | DATETIME | | Last invocation |
| use_count | INTEGER | NOT NULL, DEFAULT 0 | Total invocations |
| success_rate | REAL | NOT NULL, DEFAULT 0.0 | Tracked over time |
| execution_type | TEXT | NOT NULL, CHECK IN (prompt_template, code_procedure, tool_invocation, composite) | How the skill runs |

### skill_implementations

Versioned executable code per skill. Only one version active at a time.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| skill_id | TEXT | NOT NULL, FK → skills.id | Parent skill |
| version | INTEGER | NOT NULL | Matches skill version |
| language | TEXT | NOT NULL, CHECK IN (python, bash, prompt_template, javascript, composite) | Implementation language |
| code | TEXT | NOT NULL | Full source text |
| content_hash | TEXT | NOT NULL | SHA-256 for change detection |
| dependencies | JSON | | Required packages/modules |
| created_at | DATETIME | NOT NULL, DEFAULT now | Version creation time |
| is_active | BOOLEAN | NOT NULL, DEFAULT 0 | Whether this is the live version |
| execution_order | INTEGER | | For composite skill sub-steps |

### relations

Polymorphic knowledge graph. Connects any row in any table to any other. Integrity enforced by triggers.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| source_id | TEXT | NOT NULL | Source record ID |
| source_table | TEXT | NOT NULL | Source table name |
| target_id | TEXT | NOT NULL | Target record ID |
| target_table | TEXT | NOT NULL | Target table name |
| edge_type | TEXT | NOT NULL, CHECK IN (derived_from, contradicts, reinforces, applied_to, related_to, imports, configures, tests, documents, chunk_of) | Relationship type |
| weight | REAL | NOT NULL, DEFAULT 1.0 | Importance for traversal |
| created_at | DATETIME | NOT NULL, DEFAULT now | When established |
| context | TEXT | | Why this relation exists |

### entities

Normalized registry of every named entity encountered.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| canonical_name | TEXT | NOT NULL | Primary name |
| entity_type | TEXT | NOT NULL, CHECK IN (person, company, project, location, concept, document) | Classification |
| embedding | BLOB | | Vector of name + context |
| first_seen | DATETIME | NOT NULL, DEFAULT now | First encounter |
| last_seen | DATETIME | NOT NULL, DEFAULT now | Most recent encounter |
| aliases | JSON | | Alternate names |

### goals

Active objectives enabling proactive behavior.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| description | TEXT | NOT NULL | What the agent is trying to achieve |
| embedding | BLOB | | Vector for semantic matching |
| priority | INTEGER | NOT NULL, DEFAULT 0 | Rank ordering |
| status | TEXT | NOT NULL, DEFAULT 'active', CHECK IN (active, completed, paused, abandoned) | Lifecycle |
| created_at | DATETIME | NOT NULL, DEFAULT now | Established |
| deadline | DATETIME | | Target date |
| parent_goal_id | TEXT | FK → goals.id | Hierarchical decomposition |
| completed_at | DATETIME | | Completion timestamp |

### tags

Lightweight categorical layer.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| name | TEXT | NOT NULL, UNIQUE | Tag label |
| color | TEXT | | Hex color for UI |

### tag_assignments

Many-to-many join linking tags to any row in any table.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| tag_id | TEXT | NOT NULL, FK → tags.id | Tag reference |
| target_id | TEXT | NOT NULL | Tagged record ID |
| target_table | TEXT | NOT NULL | Tagged record's table |

---

## Workspace Awareness

### workspaces

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| name | TEXT | NOT NULL | Workspace name |
| root_path | TEXT | NOT NULL | Absolute filesystem path |
| workspace_type | TEXT | NOT NULL, CHECK IN (codebase, project_folder, data_directory) | Classification |
| created_at | DATETIME | NOT NULL, DEFAULT now | Registration time |
| last_scanned | DATETIME | | Last full scan |
| metadata | JSON | | Language, framework, build system |

### workspace_files

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| workspace_id | TEXT | NOT NULL, FK → workspaces.id | Parent workspace |
| relative_path | TEXT | NOT NULL | Path from workspace root |
| file_type | TEXT | NOT NULL, CHECK IN (python, config, markdown, image, binary, directory) | File classification |
| depth | INTEGER | NOT NULL, DEFAULT 0 | Directory depth |
| size_bytes | INTEGER | | File size |
| file_last_modified | DATETIME | | Filesystem modification time |
| last_scanned | DATETIME | | Last agent read |
| content_hash | TEXT | | SHA-256 for change detection |
| embedding | BLOB | | Vector from contents/summary |
| summary | TEXT | | Agent's understanding of the file |

---

## Operational Support

### sessions

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| started_at | DATETIME | NOT NULL, DEFAULT now | Session start |
| ended_at | DATETIME | | Session end |
| summary | TEXT | | Generated at close |
| embedding | BLOB | | Vector of summary |
| status | TEXT | NOT NULL, DEFAULT 'active', CHECK IN (active, closed) | Lifecycle |
| workspace_id | TEXT | FK → workspaces.id | Associated workspace |

### meta_config

All settings stored in-database for portability.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| key | TEXT | NOT NULL, UNIQUE | Setting name |
| value | TEXT | NOT NULL | Setting value |
| updated_at | DATETIME | NOT NULL, DEFAULT now | Last modification |

### contradictions

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| memory_a_id | TEXT | NOT NULL | First conflicting memory |
| memory_a_table | TEXT | NOT NULL | Its table |
| memory_b_id | TEXT | NOT NULL | Second conflicting memory |
| memory_b_table | TEXT | NOT NULL | Its table |
| resolution | TEXT | NOT NULL, DEFAULT 'unresolved', CHECK IN (a_kept, b_kept, both_revised, merged, unresolved) | Outcome |
| reasoning | TEXT | | Why this resolution |
| resolved_at | DATETIME | | When resolved |
| resolved_by | TEXT | CHECK IN (agent, user) or NULL | Who resolved |

### audit_log

Immutable forensic record.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| timestamp | DATETIME | NOT NULL, DEFAULT now | When |
| table_name | TEXT | NOT NULL | Affected table |
| row_id | TEXT | NOT NULL | Affected row |
| operation | TEXT | NOT NULL, CHECK IN (insert, update, delete, promote, demote) | What happened |
| before_snapshot | JSON | | State before (optional for inserts) |
| after_snapshot | JSON | | State after |
| triggered_by | TEXT | NOT NULL, CHECK IN (consolidation, user_feedback, agent_inference, migration, markdown_import, manual) | Cause |

### feedback

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| target_id | TEXT | NOT NULL | Annotated record |
| target_table | TEXT | NOT NULL | Its table |
| feedback_type | TEXT | NOT NULL, CHECK IN (correction, endorsement, annotation, deletion_request) | Type |
| content | TEXT | NOT NULL | Feedback text |
| created_at | DATETIME | NOT NULL, DEFAULT now | Submitted |
| processed | BOOLEAN | NOT NULL, DEFAULT 0 | Picked up by consolidation |

### context_snapshots

Exact knowledge state at decision time.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| timestamp | DATETIME | NOT NULL, DEFAULT now | Snapshot time |
| trigger_description | TEXT | NOT NULL | What prompted the decision |
| memory_ids | JSON | | Array of {id, table} |
| skill_ids | JSON | | Skill IDs in play |
| relation_ids | JSON | | Relations traversed |
| goal_id | TEXT | FK → goals.id | Driving goal |
| outcome | TEXT | | What the agent did |

### notification_queue

Proactive alerts from goal monitoring and sleep-time processing.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| agent_id | TEXT | NOT NULL, DEFAULT 'default' | Source agent |
| trigger_type | TEXT | NOT NULL, CHECK IN (goal_match, alert_condition, contradiction_detected, consolidation_complete) | What triggered it |
| title | TEXT | NOT NULL | Short title |
| body | TEXT | | Detail text |
| priority | TEXT | NOT NULL, DEFAULT 'medium', CHECK IN (low, medium, high, critical) | Urgency |
| related_ids | JSON | | Array of {id, table} for triggering records |
| created_at | DATETIME | NOT NULL, DEFAULT now | Generated |
| read | BOOLEAN | NOT NULL, DEFAULT 0 | Operator acknowledged |
| delivered | BOOLEAN | NOT NULL, DEFAULT 0 | Sent to tray/webhook |

---

## Performance Optimization

### views

Saved graph projections for mind-map visualization.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| name | TEXT | NOT NULL | View name |
| center_node_id | TEXT | NOT NULL | Focal point record |
| center_node_table | TEXT | NOT NULL | Focal point table |
| depth_limit | INTEGER | NOT NULL, DEFAULT 2 | Traversal depth |
| filters | JSON | | Weight, edge type, time, confidence filters |
| layout_hints | JSON | | Colors, grouping, collapsed branches |

### embeddings_cache

Precomputed similarity scores.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| node_a_id | TEXT | NOT NULL | First node |
| node_a_table | TEXT | NOT NULL | First node's table |
| node_b_id | TEXT | NOT NULL | Second node |
| node_b_table | TEXT | NOT NULL | Second node's table |
| similarity_score | REAL | NOT NULL | Cosine similarity |
| computed_at | DATETIME | NOT NULL, DEFAULT now | For cache invalidation |

---

---

## Additional Operational Tables (v1.5+)

### llm_providers

Canonical registry of configured LLM providers. Replaces flat meta_config LLM keys.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| name | TEXT | NOT NULL | Human-readable name (e.g., "Production Claude") |
| provider_type | TEXT | NOT NULL, CHECK IN (claude, openai, local) | Provider classification |
| api_key | TEXT | | Provider API key |
| model | TEXT | | Model identifier |
| endpoint | TEXT | | Custom endpoint URL |
| is_default | INTEGER | NOT NULL, DEFAULT 0 | 1 for active default provider |
| description | TEXT | | Operator notes |
| created_at | TEXT | NOT NULL, DEFAULT now | Registration timestamp |

### conversation_threads

Named, resumable conversation groupings spanning multiple sessions.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| name | TEXT | NOT NULL | Thread name |
| agent_id | TEXT | | References agents.id |
| created_at | DATETIME | NOT NULL, DEFAULT now | Creation timestamp |
| last_active | DATETIME | | Last message timestamp |
| summary | TEXT | | Auto-generated rolling summary |
| summary_embedding | BLOB | | Vector of summary |
| status | TEXT | NOT NULL, DEFAULT 'active' | active / archived |
| pinned | BOOLEAN | NOT NULL, DEFAULT 0 | Pinned to top |
| metadata | JSON | | Operator-defined labels |

### file_attachments

Files uploaded through the chat console with extracted content.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| session_id | TEXT | FK → sessions.id | Associated session |
| filename | TEXT | NOT NULL | Original filename |
| mime_type | TEXT | | Detected MIME type |
| size_bytes | INTEGER | | File size |
| extraction_method | TEXT | | pdf / text / code / csv |
| extracted_text | TEXT | | Full extracted content |
| extracted_embedding | BLOB | | Vector of extracted content |
| chunk_count | INTEGER | | Chunks created in STM |
| stm_ids | JSON | | Array of STM IDs from this file |
| uploaded_at | DATETIME | NOT NULL, DEFAULT now | Upload timestamp |

### channel_configs

External messaging channel configurations.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| name | TEXT | NOT NULL | Channel display name |
| channel_type | TEXT | NOT NULL | email / whatsapp / sms / imessage |
| config | JSON | | Channel-specific credentials and settings |
| authorized_senders | JSON | | Allowed sender addresses/numbers |
| is_active | BOOLEAN | NOT NULL, DEFAULT 0 | Whether channel is enabled |
| created_at | DATETIME | NOT NULL, DEFAULT now | Registration timestamp |

### channel_messages

Immutable log of inbound and outbound messages across channels.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| channel_id | TEXT | FK → channel_configs.id | Source channel |
| direction | TEXT | NOT NULL | inbound / outbound |
| sender | TEXT | | Sender address/number |
| content | TEXT | NOT NULL | Message text |
| timestamp | DATETIME | NOT NULL, DEFAULT now | Message timestamp |

### autonomous_tasks

Task queue for background autonomous execution.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| title | TEXT | NOT NULL | Task title |
| goal | TEXT | NOT NULL | What to accomplish |
| agent_id | TEXT | | Assigned agent |
| status | TEXT | NOT NULL, DEFAULT 'pending' | pending / running / paused / completed / failed / cancelled / timeout |
| plan | JSON | | Structured execution plan |
| max_iterations | INTEGER | DEFAULT 50 | Safety limit |
| created_at | DATETIME | NOT NULL, DEFAULT now | Creation timestamp |

### task_steps

Individual steps within an autonomous task.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| task_id | TEXT | FK → autonomous_tasks.id | Parent task |
| step_number | INTEGER | NOT NULL | Step ordering |
| description | TEXT | | Step description |
| status | TEXT | NOT NULL, DEFAULT 'pending' | Step lifecycle |
| reasoning | TEXT | | LLM reasoning trace |
| result | JSON | | Step output |
| created_at | DATETIME | NOT NULL, DEFAULT now | Timestamp |

### task_actions

Atomic action log for tool calls during task execution.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| task_id | TEXT | FK → autonomous_tasks.id | Parent task |
| step_id | TEXT | FK → task_steps.id | Parent step |
| action_type | TEXT | NOT NULL | file_read / file_write / shell / skill / memory / web |
| inputs | JSON | | Action inputs |
| outputs | JSON | | Action results |
| status | TEXT | NOT NULL | success / failed / blocked |
| created_at | DATETIME | NOT NULL, DEFAULT now | Timestamp |

### file_access_grants

Operator-approved filesystem directories for agent access.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| agent_id | TEXT | | FK → agents.id; null = all agents |
| directory_path | TEXT | NOT NULL | Absolute path |
| permissions | TEXT | NOT NULL, DEFAULT 'read' | read / read_write |
| recursive | BOOLEAN | NOT NULL, DEFAULT 1 | Include subdirectories |
| created_at | DATETIME | NOT NULL, DEFAULT now | Grant creation time |

### shell_command_log

Immutable log of shell commands executed by agents.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| task_id | TEXT | | FK → autonomous_tasks.id |
| agent_id | TEXT | | FK → agents.id |
| command | TEXT | NOT NULL | Command string |
| working_directory | TEXT | | Execution directory |
| stdout | TEXT | | Captured stdout |
| stderr | TEXT | | Captured stderr |
| exit_code | INTEGER | | Process exit code |
| executed_at | DATETIME | NOT NULL, DEFAULT now | Execution timestamp |
| duration_ms | INTEGER | | Wall-clock time |
| status | TEXT | NOT NULL | success / failed / timeout / blocked |

### skill_executions

Log of every skill execution attempt.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID |
| skill_id | TEXT | FK → skills.id | Executed skill |
| agent_id | TEXT | | Executing agent |
| started_at | DATETIME | NOT NULL, DEFAULT now | Start timestamp |
| completed_at | DATETIME | | End timestamp |
| duration_ms | INTEGER | | Wall-clock time |
| status | TEXT | NOT NULL | success / failed / timeout |
| inputs | JSON | | Input values |
| outputs | JSON | | Output values |
| stdout | TEXT | | Captured stdout |
| stderr | TEXT | | Captured stderr |
| exit_code | INTEGER | | Process exit code |

---

## FTS5 Virtual Tables

For BM25 keyword search (created if SQLite FTS5 extension is available):

- `short_term_memory_fts` — indexes `short_term_memory.content`
- `midterm_memory_fts` — indexes `midterm_memory.content`
- `long_term_memory_fts` — indexes `long_term_memory.content`

---

## Indexes

39+ indexes covering foreign keys, status fields, timestamps, confidence scores, agent IDs, notification priority/read status, cache lookup keys, provider defaults, thread status, and channel types. See `schema.py` `CREATE_INDEXES` for the full set.
