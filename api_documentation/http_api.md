# HTTP API Reference

Default base URL: `http://127.0.0.1:8420`

The API has three surfaces:

| Surface | Prefix | Auth |
|---|---|---|
| **Operator API** | `/api/...` | `Authorization: Bearer <key>` if `operator_api_key` is set; open otherwise |
| **Agent API** | `/api/agent/...` | `X-API-Key: <agent_key>` if `agent_api_key` is set; open otherwise |
| **Static UI** | `/` | none; same-origin fetch from the bundled web UI |

All responses use this envelope:

```json
{ "status": "ok" | "error",
  "data": <result> | null,
  "error": <message> | null }
```

(One exception: `POST /api/memories/export` with `format: "csv"` streams a
CSV attachment instead of the JSON envelope.)

## Lifecycle / health

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | unauthenticated liveness probe; `{status: "ok", locked: false, uptime_seconds, version, database_path, database}` — the identity fields let clients detect a server on a shared port that is backed by a different database file |
| GET | `/api/agent/health` | unauthenticated; DB status, uptime, embedding model, last consolidation |
| GET | `/api/stats` | row counts + provider name + query-cache metrics |

When the server starts in locked mode (encrypted DB, no passphrase),
`/api/health` returns `{"status":"locked","locked":true}` and most
other endpoints return **HTTP 423 Locked**. Use `/api/encryption/unlock`
to exit locked mode.

## Memory tier endpoints

```
GET    /api/memories/{tier}              ?limit=100&offset=0
POST   /api/memories/{tier}              {content, source, agent_id?, ...}
GET    /api/memories/{tier}/{id}         row + relations + tags + feedback
PUT    /api/memories/{tier}/{id}         partial update (only allowed fields)
DELETE /api/memories/{tier}/{id}
POST   /api/memories/search              {query, tiers?: [...], limit?}
POST   /api/memories/export              {format?: "json"|"csv", filters?}
```

`tier` is one of `short`, `mid`, `long`. List order is newest-first;
there is no status filter. Search returns a dict keyed by tier (not a
flat list), each row carrying a `similarity_score`; `tiers` defaults to
all three and `limit` (per tier) defaults to 10.

### Batch memory ops

```
POST /api/memories/batch/pin       {ids, memory_table, agent_id?}
POST /api/memories/batch/tag       {ids, memory_table, tag_name}
POST /api/memories/batch/promote   {ids, memory_table}    # short_term -> midterm, midterm -> long_term
POST /api/memories/batch/delete    {ids, memory_table}
```

`memory_table` is one of `short_term_memory`, `midterm_memory`,
`long_term_memory`. The handler reshapes the flat `ids` list into the
`(id, table)` pairs the CRUD layer expects. Batch delete on short-term
memories is a soft delete (status -> `expired`); the single-row DELETE
removes the row.

## Pinned memories

```
GET    /api/memories/pinned                    ?agent_id=
POST   /api/memories/pin                       {memory_id, memory_table, agent_id?, priority?, label?}
PUT    /api/memories/pinned/{id}/priority      {priority}
DELETE /api/memories/pinned/{id}               returns {"unpinned": id}
```

Pinned memories always appear at the top of the retrieval payload.

## Knowledge graph

```
GET    /api/entities                  ?type=person&limit=100
POST   /api/entities                  {canonical_name, entity_type?, aliases?}
GET    /api/entities/{id}
PUT    /api/entities/{id}             partial update
DELETE /api/entities/{id}
GET    /api/entities/{id}/graph       ?depth=2  -- BFS traversal
GET    /api/entities/{id}/detail      ?memory_limit=50  -- memories + relations + co-occurring entities in one call
GET    /api/relations/{node_id}       relations whose source or target is node_id
```

The list filter parameter is `type` (not `entity_type`); `entity_type`
in the POST body defaults to `concept`.

## Goals

```
GET    /api/goals                     ?status=active
POST   /api/goals                     {description, priority?, deadline?, parent_goal_id?}
PUT    /api/goals/{id}
DELETE /api/goals/{id}
```

## Skills + executions

```
GET    /api/skills                                 ?execution_type=python
POST   /api/skills                                 {name, description, execution_type?, input_schema?, output_schema?}
GET    /api/skills/{id}/implementations
POST   /api/skills/{id}/rollback/{version}         restore an older implementation
PUT    /api/skills/{id}                            partial update
DELETE /api/skills/{id}
GET    /api/skill-executions                       ?skill_id=&limit=50
GET    /api/skill-executions/{id}
POST   /api/skill-executions                       {skill_id, inputs?, agent_id?, session_id?}
DELETE /api/skill-executions/{id}
```

`POST /api/skill-executions` runs the skill synchronously and returns
the execution result dict (`status`, `outputs`, `stdout`, ...).

## Workspaces

```
GET    /api/workspaces                          list with file_count + file_types
POST   /api/workspaces                          {name, root_path, workspace_type}
PUT    /api/workspaces/{id}
DELETE /api/workspaces/{id}                     also removes workspace_files rows
GET    /api/workspaces/{id}/files               all file rows (no query filters)
POST   /api/workspaces/{id}/scan                rescan one workspace
POST   /api/workspaces/scan                     rescan all
```

## File access grants + local system access

```
GET    /api/file-access-grants            ?agent_id=default
POST   /api/file-access-grants            {directory_path, agent_id, permission}
DELETE /api/file-access-grants/{id}

GET    /api/system/file/read              ?path=&agent_id=&binary=false
GET    /api/system/file/list              ?path=&agent_id=
GET    /api/system/file/stat              ?path=&agent_id=
POST   /api/system/file/write             {path, content, encoding?, append?, agent_id?}
POST   /api/system/shell/execute          {command, working_dir?, timeout_seconds?, agent_id?}
GET    /api/shell-log                     ?agent_id=&limit=50
```

`permission` is `read` or `read_write`. Shell exec also requires
`shell_access_enabled=true` in `meta_config` (default false).

## Encryption

```
GET    /api/encryption/status             {sqlcipher_available, db_encrypted, passphrase_set, ...}
POST   /api/encryption/unlock             {passphrase}
POST   /api/encryption/enable             {passphrase}    plaintext -> encrypted
POST   /api/encryption/disable            {passphrase}    encrypted -> plaintext
POST   /api/encryption/rekey              {old_passphrase, new_passphrase}
```

`/api/encryption/unlock` is the only `POST` that works while the server
is in locked mode. After a successful unlock, the deferred bootstrap
runs (schema migrations, ANN warmup, MCP, scheduler, etc.) and the
server transitions to fully-running.

## Configuration

```
GET    /api/config                        list all; llm_api_key / agent_api_key / operator_api_key values are masked
GET    /api/config/{key}                  single row (value NOT masked)
PUT    /api/config/{key}                  {value}   stored stringified
GET    /api/config/alert-rules            structured custom-alert rules
POST   /api/config/alert-rules            {rules: [...]}
```

Alert rules are stored under the `custom_alert_rules` config key; the
`/api/config/alert-rules` routes are a typed wrapper around it.
Every settable key is documented in [configuration.md](configuration.md).

## LLM providers

```
GET    /api/providers                          list; api_key masked to last 4 chars
POST   /api/providers                          {name, provider_type?, model, api_key?, endpoint?, is_default?}
PUT    /api/providers/{id}                     partial update; returns {"updated": id}
DELETE /api/providers/{id}
POST   /api/providers/{id}/test                live connectivity check
POST   /api/providers/ollama/discover          {endpoint?} -> probes /api/tags
```

`provider_type` is one of: `claude`, `openai`, `ollama`, `llamacpp`,
`lmstudio`, `local`, `custom`.

## Notifications

```
GET    /api/notifications                          ?read=0&priority=high&agent_id=&limit=100
PUT    /api/notifications/{id}/read
POST   /api/notifications/{id}/deliver             retry single webhook delivery
POST   /api/notifications/dismiss                  delete read notifications
POST   /api/notifications/test-webhook             send synthetic ping
POST   /api/notifications/deliver-pending          flush all undelivered
```

## Scheduled tasks

```
GET    /api/scheduled-tasks                  ?status=active&agent_id=&limit=100&offset=0
POST   /api/scheduled-tasks                  {name, action_type, interval_seconds, ...}
GET    /api/scheduled-tasks/{id}
PUT    /api/scheduled-tasks/{id}
DELETE /api/scheduled-tasks/{id}
POST   /api/scheduled-tasks/{id}/run         run-now bypassing the schedule
GET    /api/scheduler/status                 enabled, runner_started, last_result
```

## Agent API (for AI agents calling swadb)

```
GET    /api/agent/health                     unauthenticated probe
GET    /api/agent/identity                   default-agent identity memories
POST   /api/agent/context                    {query, agent_id?, filters?, include_agents?}
POST   /api/agent/ingest                     {content, source?, session_id?, agent_id?}
POST   /api/agent/ingest/batch               {observations: [{content, source?, session_id?}, ...]}
POST   /api/agent/skill/match                {description}
POST   /api/agent/skill/execute              {skill_id, inputs?}
POST   /api/agent/goals/check                {context}
POST   /api/agent/session/start              {workspace_id?, thread_id?, provider_id?}
POST   /api/agent/session/end                {session_id, summary?}
POST   /api/agent/chat                       {message, session_id, history?, agent_id?, provider?, model?}
```

`session_id` is **required** for `/api/agent/chat` — obtain one from
`/api/agent/session/start`. These are the same operations exposed via
MCP — see [mcp.md](mcp.md).

## Conversation threads

```
GET    /api/threads                       ?agent_id=&status=&limit=50
POST   /api/threads                       {name, agent_id?, description?, metadata?}
GET    /api/threads/{id}
PUT    /api/threads/{id}                  {name?, description?, status?, metadata?}
DELETE /api/threads/{id}
GET    /api/threads/{id}/messages         ?limit=100&offset=0
```

## Agent registry

```
GET    /api/agents
POST   /api/agents                        {id, name, description?, config?}
GET    /api/agents/{id}
PUT    /api/agents/{id}                   partial update
POST   /api/agents/{id}/rotate-key        mint + store a per-agent API key
```

Per-agent keys are additive: the global `agent_api_key` stays in effect,
and a rotated per-agent key authenticates that agent specifically.

## Attachments, uploads, chat files

```
GET    /api/attachments                   ?session_id=&limit=50
GET    /api/attachments/{id}
POST   /api/uploads                       {filename, data (base64), content_type?} -> {id, url, size}
GET    /api/uploads/{name}                serves the stored file bytes
POST   /api/chat/file                     {filename, data (base64), session_id?, thread_id?, agent_id?}
```

`/api/chat/file` extracts text from the uploaded file and ingests it as
a file attachment tied to the session/thread.

## Autonomous tasks

```
GET    /api/tasks                         ?status=&limit=50
POST   /api/tasks                         {name, goal, agent_id?, constraints?, max_steps?, require_approval?}
GET    /api/tasks/{id}
PUT    /api/tasks/{id}                    {name?, goal?, status?, constraints?, max_steps?, require_approval?}
DELETE /api/tasks/{id}
GET    /api/tasks/{id}/steps
GET    /api/tasks/{id}/actions
POST   /api/tasks/{id}/start
POST   /api/tasks/{id}/pause
POST   /api/tasks/{id}/cancel
POST   /api/tasks/{id}/approve            {step_id, approved?, feedback?}
```

## Channels

```
GET    /api/channels
POST   /api/channels                      {channel_type, name, credentials?, settings?, agent_id?}
GET    /api/channels/{id}                 credentials masked
PUT    /api/channels/{id}                 {name?, credentials?, settings?, enabled?}
DELETE /api/channels/{id}
GET    /api/channels/{id}/messages        ?limit=50&direction=
POST   /api/channels/{id}/messages        {content, direction?, sender?, recipient?, external_id?, metadata?}
```

## Contradictions, feedback, audit, views

```
GET    /api/contradictions                ?resolution=unresolved
POST   /api/contradictions/{id}/resolve   {resolution, reasoning?, resolved_by?}
POST   /api/feedback                      {target_id, target_table, feedback_type, content}
DELETE /api/feedback/{id}
GET    /api/audit                         ?table_name=&operation=&triggered_by=&limit=100&offset=0
GET    /api/views                         saved graph views
POST   /api/views                         {name, center_node_id, center_node_table, depth_limit?, filters?, layout_hints?}
```

## Markdown + import

```
POST   /api/markdown/submit               ingest a markdown document
POST   /api/markdown/batch                ingest many documents at once
GET    /api/markdown/watcher/status
GET    /api/markdown/reverse/{table}/{id} render a row back to markdown
POST   /api/import                        {file_path, provider}   ChatGPT/Claude export importer
GET    /api/import/status                 last import result, or {"status": "idle"}
```

## Status probes

```
GET    /api/mcp/status                    MCP transport, port, tool list
GET    /api/git-sync/status
GET    /api/idle/status                   {is_idle, idle_since}
```

## Maintenance

```
POST   /api/maintenance/consolidate          run consolidation cycle now
POST   /api/maintenance/sleep-cycle          run full sleep cycle now
POST   /api/maintenance/integrity-check
POST   /api/maintenance/ann-rebuild
GET    /api/maintenance/ann-status
POST   /api/maintenance/cache-clear
POST   /api/maintenance/git-sync             pull+process knowledge git repo
```

## DB Console

```
POST   /api/db/query                          {sql}                    safe SELECT/PRAGMA/EXPLAIN/WITH; INSERT/UPDATE/DELETE require write_enabled config
POST   /api/db/ai-query                       {question}               LLM generates SQL
GET    /api/db-query/schema                   table list with DDL
GET    /api/db-query/history                  last 50 successful queries
DELETE /api/db-query/history                  clear
```

ATTACH / DETACH / DROP / ALTER are **always blocked**, even with write
mode enabled.

## Conventions

- `DELETE` endpoints return `200 {"deleted": id}` (or `{"unpinned": id}`
  for pins) unconditionally — deleting an id that doesn't exist is not an
  error. Confirm removal with a follow-up GET (404).
- List endpoints strip `embedding` blobs from every row.
- `201` is used for resource creation, `200` for everything else.

## Common error codes

| Code | Meaning |
|---|---|
| 400 | Bad request — bad input shape, validation failure, etc. |
| 401 | Auth required (`operator_api_key` or `agent_api_key` set, missing/wrong) |
| 403 | Permission denied (e.g. write query when read-only mode, file access denied by grant) |
| 404 | Not found |
| 408 | Query timed out (5s default for DB Console) |
| 423 | **Locked** — DB is encrypted and no passphrase available; use `/api/encryption/unlock` |
| 500 | Server error |
| 502 | Webhook POST failed during retry-delivery |
