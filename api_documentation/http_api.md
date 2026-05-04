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

## Lifecycle / health

| Method | Path | Notes |
|---|---|---|
| GET | `/api/agent/health` | unauthenticated probe; returns server uptime |
| GET | `/api/health` | operator-side health |
| GET | `/api/stats` | row counts + provider name + query-cache hit rate + queue depths |

When the server starts in locked mode (encrypted DB, no passphrase),
`/api/health` returns `{"status":"locked","locked":true}` and most
other endpoints return **HTTP 423 Locked**. Use `/api/encryption/unlock`
to exit locked mode.

## Memory tier endpoints

```
GET    /api/memories/{tier}              ?limit=50&offset=0&status=active
POST   /api/memories/{tier}              {content, source, agent_id?, ...}
GET    /api/memories/{tier}/{id}
PUT    /api/memories/{tier}/{id}         partial update (only allowed fields)
DELETE /api/memories/{tier}/{id}
POST   /api/memories/search              {query, tiers:[...], limit, agent_id?}
```

`tier` is one of `short`, `mid`, `long`.

### Batch memory ops

```
POST /api/memories/batch/pin       {ids, memory_table, agent_id?}
POST /api/memories/batch/tag       {ids, memory_table, tag_name}
POST /api/memories/batch/promote   {ids, memory_table}    # short_term -> midterm, midterm -> long_term
POST /api/memories/batch/delete    {ids, memory_table}
```

`memory_table` is one of `short_term_memory`, `midterm_memory`,
`long_term_memory`. The handler reshapes the flat `ids` list into the
`(id, table)` pairs the CRUD layer expects.

## Pinned memories

```
GET    /api/memories/pinned                    list
POST   /api/memories/pin                       {memory_id, memory_table, agent_id?, label?}
PUT    /api/memories/pinned/{id}/priority      {priority}
DELETE /api/memories/pinned/{id}
```

Pinned memories always appear at the top of the retrieval payload.

## Knowledge graph

```
GET    /api/entities                  ?entity_type=person&limit=50
POST   /api/entities                  {canonical_name, entity_type, aliases?}
GET    /api/entities/{id}
PUT    /api/entities/{id}             partial update
DELETE /api/entities/{id}
GET    /api/entities/{id}/graph       ?depth=2  -- BFS traversal
GET    /api/entities/{id}/detail      ?memory_limit=50  -- memories + relations + co-occurring entities in one call
GET    /api/relations/{node_id}       relations whose source or target is node_id
```

## Goals

```
GET    /api/goals
POST   /api/goals                     {description, criteria?, status?}
PUT    /api/goals/{id}
DELETE /api/goals/{id}
```

## Skills

```
GET    /api/skills                                 ?execution_type=python
POST   /api/skills                                 {name, description, execution_type, ...}
GET    /api/skills/{id}/implementations
POST   /api/skills/{id}/rollback/{version}         restore an older implementation
PUT    /api/skills/{id}                            partial update
DELETE /api/skills/{id}
POST   /api/skill-executions                       {skill_id, inputs?, agent_id?}
DELETE /api/skill-executions/{id}
```

## Workspaces

```
GET    /api/workspaces                          list with file_count + file_types
POST   /api/workspaces                          {name, root_path, workspace_type}
PUT    /api/workspaces/{id}
DELETE /api/workspaces/{id}                     also removes workspace_files rows
GET    /api/workspaces/{id}/files               ?file_type=python&limit=200
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
GET    /api/config                        list all (sensitive values masked)
GET    /api/config/{key}
PUT    /api/config/{key}                  {value}
GET    /api/config/alert-rules            structured custom-alert rules
POST   /api/config/alert-rules            {rules: [...]}
```

Every settable key is documented in [configuration.md](configuration.md).

## LLM providers

```
GET    /api/providers                          list
POST   /api/providers                          {name, provider_type, model, api_key?, endpoint?}
PUT    /api/providers/{id}                     partial update
DELETE /api/providers/{id}
POST   /api/providers/{id}/test                live connectivity check
POST   /api/providers/ollama/discover          {endpoint?} -> probes /api/tags
```

`provider_type` is one of: `claude`, `openai`, `ollama`, `llamacpp`,
`lmstudio`, `local`, `custom`.

## Notifications

```
GET    /api/notifications                          ?read=0&priority=high&limit=100
PUT    /api/notifications/{id}/read
POST   /api/notifications/{id}/deliver             retry single webhook delivery
POST   /api/notifications/dismiss                  delete read notifications
POST   /api/notifications/test-webhook             send synthetic ping
POST   /api/notifications/deliver-pending          flush all undelivered
```

## Scheduled tasks

```
GET    /api/scheduled-tasks                  ?status=active
POST   /api/scheduled-tasks                  {name, action_type, interval_seconds, ...}
PUT    /api/scheduled-tasks/{id}
DELETE /api/scheduled-tasks/{id}
POST   /api/scheduled-tasks/{id}/run         run-now bypassing the schedule
GET    /api/scheduler/status                 enabled, runner_started, last_result
```

## Agent API (for AI agents calling swadb)

```
POST   /api/agent/chat                       {message, history, session_id?, provider?}
POST   /api/agent/context                    {query, agent_id?, filters?}
POST   /api/agent/ingest                     {content, source}
GET    /api/agent/identity                   default-agent identity memories
```

These are the same endpoints exposed via MCP — see [mcp.md](mcp.md).

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
