# Configuration Reference

Every behavioral knob in swadb lives in the `meta_config` table. Read
and update via:

- The **Settings UI** (most knobs are categorized)
- `swadb config get/set/list` from the CLI
- `GET/PUT /api/config/{key}` from HTTP

A fresh `swadb init` seeds 63 default keys. Below is the complete
reference grouped by area.

## Core memory

| Key | Default | Notes |
|---|---|---|
| `embedding_model` | `all-MiniLM-L6-v2` | sentence-transformers model name |
| `embedding_dimensions` | `384` | informational; matches the model |
| `consolidation_enabled` | `true` | run consolidation cycles automatically |
| `consolidation_interval_seconds` | `300` | minimum seconds between cycles |
| `decay_enabled` | `true` | apply decay to confidence/relevance over time |
| `decay_rate_multiplier` | `1.0` | speed of decay (1.0 = normal) |
| `stm_default_ttl_seconds` | `3600` | TTL for short-term memories before expiry |
| `promotion_confidence_threshold` | `0.8` | min confidence to promote STM → MTM |
| `clustering_similarity_threshold` | `0.85` | cosine threshold for memory clustering during consolidation |
| `staleness_threshold_days` | `90` | days before a memory is considered stale |
| `orphan_handling_mode` | `flag` | `flag` or `delete` for orphaned memories |
| `min_relation_weight` | `0.05` | drop relations below this weight during pruning |

## Retrieval pipeline

| Key | Default | Notes |
|---|---|---|
| `context_results_per_tier` | `10` | max memories per tier in retrieval payload |
| `goal_similarity_threshold` | `0.7` | min similarity to match goals |
| `skill_similarity_threshold` | `0.6` | min similarity to match skills |
| `bm25_enabled` | `true` | run BM25 keyword search alongside semantic |
| `graph_traversal_enabled` | `true` | walk knowledge graph during retrieval |
| `temporal_boost_enabled` | `true` | boost recent memories |
| `temporal_decay_curve` | `0.95` | how quickly temporal boost decreases (0=fast, 1=slow) |
| `reranker_enabled` | `false` | use cross-encoder to re-rank top results |
| `reranker_model` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | model name |
| `reranker_candidates` | `20` | rerank top-N candidates |
| `max_context_tokens` | `4000` | rough budget for context payload size |

## Sleep cycle

| Key | Default | Notes |
|---|---|---|
| `sleep_idle_threshold_seconds` | `300` | seconds of inactivity before triggering a sleep cycle |
| `sleep_reflection_enabled` | `true` | run sleep cycles automatically |
| `sleep_goal_monitor_window_hours` | `24` | look-back window for goal monitoring |
| `sleep_graph_pruning_threshold_days` | `60` | days before pruning low-weight relations |
| `sleep_pre_compute_enabled` | `true` | warm the query cache for frequent queries |
| `sleep_pre_compute_top_n` | `10` | how many frequent queries to pre-compute |
| `cache_ttl_hours` | `24` | TTL for cached query results |

## ANN (HNSW) index

| Key | Default | Notes |
|---|---|---|
| `ann_index_enabled` | `true` | use HNSW for semantic search if available |
| `ann_rebuild_strategy` | `after_consolidation` | when to rebuild indexes |

Requires `pip install swadb[ann]`. Falls back to brute force when
disabled or `hnswlib` isn't installed.

## Encryption

| Key | Default | Notes |
|---|---|---|
| `encryption_enabled` | `false` | informational flag; flipped automatically by encrypt/disable flows |

The actual passphrase lives in process memory (set via Unlock screen
or `SWADB_PASSPHRASE` env var) — never in the config table.

## Notifications

| Key | Default | Notes |
|---|---|---|
| `notification_webhook_url` | `""` | POST notifications here as JSON |
| `notification_priority_threshold` | `medium` | min priority to deliver — `low` / `medium` / `high` / `critical` |

## Scheduler

| Key | Default | Notes |
|---|---|---|
| `scheduler_enabled` | `true` | run scheduled tasks |
| `scheduler_poll_interval_seconds` | `5` | how often to check the queue |

## MCP server

| Key | Default | Notes |
|---|---|---|
| `mcp_enabled` | `true` | auto-start MCP alongside HTTP serve |
| `mcp_transport` | `sse` | `sse` or `stdio` |
| `mcp_port` | `8421` | SSE bind port |

## Markdown / file authoring

| Key | Default | Notes |
|---|---|---|
| `markdown_inbox_path` | `""` | watch directory for new markdown files |
| `markdown_watch_enabled` | `false` | poll the inbox |
| `markdown_watch_interval_seconds` | `5` | poll interval |
| `max_file_context_tokens` | `2000` | budget for inline file contents in context |

## Git knowledge sync

| Key | Default | Notes |
|---|---|---|
| `knowledge_git_repo` | `""` | local path to the git repo |
| `knowledge_git_branch` | `main` | branch to track |
| `knowledge_git_auto_commit` | `false` | auto-commit UI edits back to the repo |
| `last_git_sync_commit` | `""` | last successfully-synced commit (state, not config) |
| `last_git_sync_at` | `""` | timestamp |

## DB Console

| Key | Default | Notes |
|---|---|---|
| `db_console_write_enabled` | `false` | allow INSERT/UPDATE/DELETE in DB Console (ATTACH/DROP/ALTER are always blocked) |
| `db_query_timeout_seconds` | `5` | interrupt runaway queries after this many seconds |

## Skills

| Key | Default | Notes |
|---|---|---|
| `skill_timeout_seconds` | `30` | max wall time for sandboxed skill exec |
| `skill_max_memory_mb` | `256` | resource limit |
| `skill_allow_network` | `false` | allow skills to make outbound calls |

## Local system access

| Key | Default | Notes |
|---|---|---|
| `shell_access_enabled` | `false` | allow `execute_shell` calls (off by default) |
| `shell_timeout_seconds` | `30` | default per-command timeout |
| `shell_max_timeout_seconds` | `300` | hard ceiling on per-call override |
| `shell_denied_keywords` | `""` | empty = use built-in defaults; JSON list overrides |

Built-in deny list: `rm -rf /`, `rm -rf ~`, `:(){:|:&};:` (fork bomb),
`mkfs`, `format c:`, `dd if=`, `> /dev/sda`, `shutdown`, `reboot`,
`halt`. These are typo backstops, not a security boundary.

## API auth

| Key | Default | Notes |
|---|---|---|
| `agent_api_key` | `""` | required `X-API-Key` header for `/api/agent/*` if set |
| `operator_api_key` | `""` | required `Authorization: Bearer` for `/api/*` if set |

Empty values mean "open access" — only safe on localhost-only deployments.

## UI

| Key | Default | Notes |
|---|---|---|
| `theme_preference` | `auto` | `auto` / `light` / `dark` |

## LLM provider (legacy / write-only)

These flat keys are **deprecated**. The `llm_providers` table is the
single source of truth. New databases don't seed these keys; old
databases continue to receive write-only sync from the default
provider.

| Key | Default (old DBs only) | Notes |
|---|---|---|
| `llm_provider` | `claude` | DEPRECATED — use llm_providers table |
| `llm_api_key` | `""` | DEPRECATED |
| `llm_model` | `claude-sonnet-4-20250514` | DEPRECATED |
| `llm_endpoint` | `""` | DEPRECATED |
| `active_provider_id` | `""` | id of the currently-active provider in `llm_providers` |

## Custom alerts

| Key | Default | Notes |
|---|---|---|
| `custom_alert_rules` | `[]` | JSON array of alert-condition rules; see Settings → Alert Conditions |

## Internal state (not user-tunable)

These keys store runtime state and should not normally be edited by
hand:

- `last_sleep_cycle_timestamp`
- `db_query_history` (last 50 successful manual SQL queries)
