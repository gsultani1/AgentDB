# AgentDB API Reference

All endpoints are served on `http://127.0.0.1:8420` by default. All responses use the envelope `{ status, data, error }`. Content-Type is `application/json` for all requests and responses.

---

## Operator API

Serves the management UI. Base path: `/api/`

### Dashboard

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/stats` | Aggregate statistics: row counts for all tables, unresolved contradictions, pending feedback, active goals, unread notifications, LLM provider, embedding model, file watcher status, agent count |

### Memories

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/memories/{tier}` | List memories. Tier: `short`, `mid`, `long`. Query params: `limit`, `offset` |
| GET | `/api/memories/{tier}/{id}` | Single memory with relations, tags, and feedback history |
| POST | `/api/memories/{tier}` | Create a memory. Body: `{ content, category, confidence, source, agent_id, provenance }` |
| PUT | `/api/memories/{tier}/{id}` | Update a memory. Body: any updatable field |
| DELETE | `/api/memories/{tier}/{id}` | Delete a memory. Cascade triggers clean up relations, tags, feedback |
| POST | `/api/memories/search` | Semantic search. Body: `{ query, tiers: ["short","mid","long"], limit }` |

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

**Create skill example:**
```json
POST /api/skills
{
  "name": "Text Summarization",
  "description": "Summarize long text into key bullet points",
  "execution_type": "prompt_template"
}
```

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

### Maintenance

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/maintenance/consolidate` | Trigger a manual consolidation cycle |
| POST | `/api/maintenance/sleep-cycle` | Trigger a manual sleep-time processing cycle |
| POST | `/api/maintenance/integrity-check` | Run orphan detection scan |

### Import

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/import` | Start migration pipeline |
| GET | `/api/import/status` | Pipeline progress |

### Workspaces

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/workspaces` | List registered workspaces |
| POST | `/api/workspaces/scan` | Trigger workspace rescan |

---

## Agent API

Called by external AI systems during inference. Base path: `/api/agent/`

All endpoints accept an optional `agent_id` parameter for multi-agent scoping (default: `"default"`).

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/agent/context` | **Primary retrieval.** Returns ranked memories, matched goals, applicable skills, expanded entities. Body: `{ query, agent_id, filters }` |
| POST | `/api/agent/ingest` | Store observation in STM. Body: `{ content, source, session_id, agent_id }` |
| POST | `/api/agent/ingest/batch` | Bulk ingest. Body: `{ observations: [{ content, source, session_id }] }` |
| POST | `/api/agent/skill/match` | Find skills by similarity. Body: `{ description }` |
| POST | `/api/agent/skill/execute` | Execute a skill. Body: `{ skill_id, inputs }` |
| POST | `/api/agent/goals/check` | Match context against goals. Body: `{ context }` |
| GET | `/api/agent/identity` | All identity + directive long-term memories |
| POST | `/api/agent/session/start` | Create session. Body: `{ workspace_id }` (optional). Returns `{ session_id }` |
| POST | `/api/agent/session/end` | Close session. Body: `{ session_id, summary }` |
| GET | `/api/agent/health` | System status: DB connectivity, uptime, embedding model, last consolidation |
| POST | `/api/agent/chat` | Full pipeline: retrieve context → call LLM → ingest exchange → return response with observability. Body: `{ message, session_id, history }` |

### Context Retrieval Example

```json
POST /api/agent/context
{
  "query": "What does the user think about cloud hosting?",
  "agent_id": "default",
  "filters": {
    "tier": ["mid", "long"],
    "confidence_min": 0.5
  }
}
```

Response:
```json
{
  "status": "ok",
  "data": {
    "memories": {
      "midterm": [
        { "id": "abc...", "content": "User prefers self-hosted solutions", "confidence": 0.85, "similarity_score": 0.82, "tier": "midterm" }
      ],
      "long_term": [
        { "id": "def...", "content": "Never recommend cloud-dependent solutions", "confidence": 1.0, "similarity_score": 0.91, "tier": "long_term" }
      ]
    },
    "entities": [],
    "goals": [],
    "skills": []
  }
}
```

### Ingestion Example

```json
POST /api/agent/ingest
{
  "content": "The user mentioned they're evaluating Hetzner for dedicated servers",
  "source": "conversation",
  "session_id": "sess-123",
  "agent_id": "default"
}
```

### Chat Pipeline Example

```json
POST /api/agent/chat
{
  "message": "What hosting options should I consider?",
  "session_id": "sess-123",
  "history": [
    { "role": "user", "content": "I need to host a Python app" },
    { "role": "assistant", "content": "What are your latency and budget requirements?" }
  ]
}
```

Response includes `response`, `context_payload`, `formatted_context`, `snapshot_id`, `ingested_ids`, `provider`, `model`, `llm_latency_seconds`.
