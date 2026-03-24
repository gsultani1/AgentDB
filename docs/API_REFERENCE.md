# AgentDB API Reference

All endpoints are served on `http://127.0.0.1:8420` by default. All responses use the envelope `{ status, data, error }`. Content-Type is `application/json` for all requests and responses.

---

## Operator API

Serves the management UI. Base path: `/api/`

### Dashboard

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/stats` | Aggregate statistics: row counts for all tables, unresolved contradictions, pending feedback, active goals, unread notifications, LLM provider, embedding model, file watcher status, agent count, cache stats |

### Memories

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/memories/{tier}` | List memories. Tier: `short`, `mid`, `long`. Query params: `limit`, `offset`, `agent_id` |
| GET | `/api/memories/{tier}/{id}` | Single memory with relations, tags, and feedback history |
| POST | `/api/memories/{tier}` | Create a memory. Body: `{ content, category, confidence, source, agent_id, provenance }` |
| PUT | `/api/memories/{tier}/{id}` | Update a memory. Body: any updatable field |
| DELETE | `/api/memories/{tier}/{id}` | Delete a memory. Cascade triggers clean up relations, tags, feedback |
| POST | `/api/memories/search` | Semantic search. Body: `{ query, tiers: ["short","mid","long"], limit, agent_id }` |
| POST | `/api/memories/export` | Export memories. Body: `{ tier, agent_id, format: "json"|"csv", filters }` |

**Pinned Memories:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/memories/pinned` | List all pinned memories for the active agent |
| POST | `/api/memories/pin` | Pin a memory. Body: `{ memory_id, memory_table, agent_id, label, priority }` |
| DELETE | `/api/memories/pin/{id}` | Unpin a memory by pinned_memories.id |
| PUT | `/api/memories/pin/{id}/priority` | Update pin priority |

**Create memory example:**
```json
POST /api/memories/long
{
  "content": "The user prefers Python for backend work",
  "category": "preference",
  "confidence": 0.95,
  "provenance": "user_authored"
}
```

### Skills

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/skills` | List all skills. Query params: `execution_type` |
| GET | `/api/skills/{id}/implementations` | All implementation versions for a skill |
| POST | `/api/skills` | Create a skill. Body: `{ name, description, execution_type, input_schema, output_schema }` |
| PUT | `/api/skills/{id}` | Update skill fields |
| POST | `/api/skills/{id}/rollback/{version}` | Rollback to a previous implementation version |
| DELETE | `/api/skills/{id}` | Delete skill and all implementations |

### Entities

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/entities` | List entities. Query params: `type`, `limit` |
| GET | `/api/entities/{id}/graph` | Subgraph centered on entity. Query params: `depth` (default 2) |
| POST | `/api/entities` | Create entity. Body: `{ canonical_name, entity_type, aliases }` |
| PUT | `/api/entities/{id}` | Update entity fields |
| DELETE | `/api/entities/{id}` | Delete entity and cascade relations |

Entity types: `person`, `company`, `project`, `location`, `concept`, `document`

### Goals

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/goals` | List goals. Query params: `status` |
| POST | `/api/goals` | Create goal. Body: `{ description, priority, deadline, parent_goal_id }` |
| PUT | `/api/goals/{id}` | Update goal fields (status, priority, etc.) |
| DELETE | `/api/goals/{id}` | Delete a goal |

### Relations

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/relations/{node_id}` | All relations where node_id is source or target |

Edge types: `derived_from`, `contradicts`, `reinforces`, `applied_to`, `related_to`, `imports`, `configures`, `tests`, `documents`, `chunk_of`

### Feedback

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/feedback` | Submit feedback. Body: `{ target_id, target_table, feedback_type, content }` |
| DELETE | `/api/feedback/{id}` | Delete a feedback entry |

Feedback types: `correction`, `endorsement`, `annotation`, `deletion_request`

### Contradictions

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/contradictions` | List contradictions. Query params: `resolution` |
| POST | `/api/contradictions/{id}/resolve` | Resolve. Body: `{ resolution, reasoning, resolved_by }` |

Resolutions: `a_kept`, `b_kept`, `both_revised`, `merged`, `unresolved`

### Agents

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/agents` | List all registered agents |
| GET | `/api/agents/{id}` | Single agent details |
| POST | `/api/agents` | Register agent. Body: `{ id, name, description, config }` |
| PUT | `/api/agents/{id}` | Update agent config |

### LLM Providers

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/providers` | List all providers |
| POST | `/api/providers` | Create a provider. Body: `{ name, provider_type, api_key, model, endpoint, is_default }` |
| GET | `/api/providers/{id}` | Get a single provider |
| PUT | `/api/providers/{id}` | Update provider configuration |
| DELETE | `/api/providers/{id}` | Remove a provider |
| POST | `/api/providers/{id}/test` | Test provider connectivity (makes a minimal API call) |
| POST | `/api/providers/{id}/set-default` | Set as the default provider |

Provider types: `claude`, `openai`, `local`

### Conversation Threads

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/threads` | List all threads for the active agent |
| POST | `/api/threads` | Create a new thread. Body: `{ name, agent_id }` |
| GET | `/api/threads/{id}` | Get thread with summary and metadata |
| PUT | `/api/threads/{id}` | Update thread name, pinned status |
| DELETE | `/api/threads/{id}` | Delete thread (memories retained) |

### Notifications

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/notifications` | List notifications. Query params: `read` (0/1), `priority`, `agent_id`, `limit` |
| PUT | `/api/notifications/{id}/read` | Mark notification as read |
| POST | `/api/notifications/dismiss` | Delete all read notifications |

Priority levels: `low`, `medium`, `high`, `critical`
Trigger types: `goal_match`, `alert_condition`, `contradiction_detected`, `consolidation_complete`

### Configuration

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/config` | All config values (API keys masked) |
| GET | `/api/config/{key}` | Single config value |
| PUT | `/api/config/{key}` | Update config. Body: `{ value }` |

### Audit Log

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/audit` | Paginated audit log. Query params: `table_name`, `operation`, `triggered_by`, `limit`, `offset` |

Operations: `insert`, `update`, `delete`, `promote`, `demote`
Triggered by: `consolidation`, `user_feedback`, `agent_inference`, `migration`, `markdown_import`, `manual`

### Markdown Authoring

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/markdown/submit` | Process a markdown document. Body: `{ text }` |
| POST | `/api/markdown/batch` | Process multiple documents. Body: `{ documents: ["...", "..."] }` |
| GET | `/api/markdown/reverse/{table}/{id}` | Reverse-generate markdown from a database record |
| GET | `/api/markdown/watcher/status` | File watcher status: enabled, inbox path, pending count |

### Views

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/views` | List saved graph views |
| POST | `/api/views` | Save a view. Body: `{ name, center_node_id, center_node_table, depth_limit, filters, layout_hints }` |

### Scheduled Tasks

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/scheduled-tasks` | List all scheduled tasks |
| POST | `/api/scheduled-tasks` | Create a scheduled task |
| PUT | `/api/scheduled-tasks/{id}` | Update a scheduled task |
| DELETE | `/api/scheduled-tasks/{id}` | Delete a scheduled task |

### Maintenance

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/maintenance/consolidate` | Trigger a manual consolidation cycle |
| POST | `/api/maintenance/sleep-cycle` | Trigger a manual sleep-time processing cycle |
| POST | `/api/maintenance/integrity-check` | Run orphan detection scan |

### Import

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/import` | Start migration pipeline. Body: `{ data, provider: "chatgpt"|"claude"|"jsonl" }` |
| GET | `/api/import/status` | Pipeline progress |

### Workspaces

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/workspaces` | List registered workspaces |
| POST | `/api/workspaces` | Register a workspace. Body: `{ name, root_path, workspace_type }` |
| POST | `/api/workspaces/scan` | Scan all workspaces |
| POST | `/api/workspaces/{id}/scan` | Scan a specific workspace |

### Git Sync

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/maintenance/git-sync` | Pull and process changed files from knowledge repo |
| GET | `/api/git-sync/status` | Last sync timestamp, commit hash, file counts |

### Encryption

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/encryption/status` | Encryption status (library availability, encrypted state) |
| POST | `/api/encryption/rekey` | Change encryption passphrase |

### DB Query

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/db-query` | Natural language to SQL query. Body: `{ question }` |
| GET | `/api/db-query/schema` | Returns all table names and column definitions |

### MCP Status

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/mcp/status` | MCP server status (port, transport, uptime, tool list, crash recovery state) |

### File Attachments

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat/file` | Upload a file for chat context extraction |

### Channels

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/channels` | List channel configurations |
| POST | `/api/channels` | Create a channel config |
| PUT | `/api/channels/{id}` | Update a channel config |
| DELETE | `/api/channels/{id}` | Delete a channel config |

### Autonomous Tasks

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/tasks` | List autonomous tasks |
| POST | `/api/tasks` | Create a task |
| POST | `/api/tasks/{id}/pause` | Pause a running task |
| POST | `/api/tasks/{id}/cancel` | Cancel a task |
| POST | `/api/tasks/{id}/approve` | Approve a human-gate checkpoint |

---

## Agent API

Called by external AI systems during inference. Base path: `/api/agent/`

All endpoints accept an optional `agent_id` parameter for multi-agent scoping (default: `"default"`).

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/agent/context` | **Primary retrieval.** 9-stage pipeline returns ranked memories, matched goals, applicable skills, expanded entities. Body: `{ query, agent_id, include_agents, filters }` |
| POST | `/api/agent/ingest` | Store observation in STM. Body: `{ content, source, session_id, agent_id }` |
| POST | `/api/agent/ingest/batch` | Bulk ingest. Body: `{ observations: [{ content, source, session_id }] }` |
| POST | `/api/agent/skill/match` | Find skills by similarity. Body: `{ description }` |
| POST | `/api/agent/skill/execute` | Execute a skill. Body: `{ skill_id, inputs }` |
| POST | `/api/agent/goals/check` | Match context against goals. Body: `{ context }` |
| GET | `/api/agent/identity` | All identity + directive long-term memories |
| POST | `/api/agent/session/start` | Create session. Body: `{ workspace_id }` (optional). Returns `{ session_id }` |
| POST | `/api/agent/session/end` | Close session. Body: `{ session_id, summary }` |
| GET | `/api/agent/health` | System status: DB connectivity, uptime, embedding model, idle_since, sleep_processor_active, MCP status |
| POST | `/api/agent/chat` | Full pipeline: retrieve context → call LLM → ingest exchange → return response with observability. Body: `{ message, session_id, provider_id }` |

### Context Retrieval Example

```bash
curl -X POST http://127.0.0.1:8420/api/agent/context \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What does the user think about cloud hosting?",
    "agent_id": "default",
    "filters": {
      "tier": ["mid", "long"],
      "confidence_min": 0.5
    }
  }'
```

Response:
```json
{
  "status": "ok",
  "data": {
    "memories": {
      "midterm": [
        { "id": "abc...", "content": "User prefers self-hosted solutions", "confidence": 0.85, "similarity_score": 0.82, "tier": "midterm", "strategy": "semantic" }
      ],
      "long_term": [
        { "id": "def...", "content": "Never recommend cloud-dependent solutions", "confidence": 1.0, "similarity_score": 0.91, "tier": "long_term", "strategy": "semantic" }
      ]
    },
    "entities": [],
    "goals": [],
    "skills": [],
    "strategies_used": ["semantic", "bm25", "graph", "temporal"],
    "snapshot_id": "snap-123..."
  }
}
```

### Ingestion Example

```bash
curl -X POST http://127.0.0.1:8420/api/agent/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "content": "The user mentioned they are evaluating Hetzner for dedicated servers",
    "source": "conversation",
    "session_id": "sess-123",
    "agent_id": "default"
  }'
```

### Chat Pipeline Example

```bash
curl -X POST http://127.0.0.1:8420/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What hosting options should I consider?",
    "session_id": "sess-123"
  }'
```

Response includes `response`, `context_payload`, `formatted_context`, `snapshot_id`, `ingested_ids`, `provider`, `model`, `llm_latency_seconds`.

---

## MCP Server

The MCP server exposes 9 tools via SSE (port 8421, auto-started) or stdio transport:

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

The MCP thread runs with crash recovery: auto-restart with 2-second delay, max 5 consecutive failures before giving up.
