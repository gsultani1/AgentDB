# Architecture (30k-foot view)

For PR-grade detail see `docs/ARCHITECTURE.md` and `docs/SCHEMA_REFERENCE.md`
in the repo root. This page is the executive summary.

## What swadb is

A self-contained agent memory system delivered as a single Python
package. One `.db` file holds the entire state.

## What swadb is NOT

- A vector database (it ships with one, but you don't bring your own)
- A graph database (same)
- A queue / scheduler / job runner (it has one, lightweight)
- An LLM (it talks to several via adapter pattern)
- A multi-tenant service (per-agent scoping is built in but no
  organization layer)

## Layered architecture

```
┌────────────────────────────────────────────────────────────────────┐
│ Web UI (single-page, served from package-data swadb/static/)       │
│ Tauri shell (optional native window)                               │
└────────────────────────────────────────────────────────────────────┘
                            │
┌────────────────────────────────────────────────────────────────────┐
│ HTTP server (60+ routes, port 8420)                                │
│ MCP server  (9 tools, SSE on 8421 or stdio)                        │
│ CLI         (subprocess invocation)                                │
└────────────────────────────────────────────────────────────────────┘
                            │
┌────────────────────────────────────────────────────────────────────┐
│ Python public API: crud, context, consolidation, sleep, ...       │
└────────────────────────────────────────────────────────────────────┘
                            │
┌────────────────────────────────────────────────────────────────────┐
│ swadb.database  — connection mgmt, SQLCipher detection,            │
│                   in-memory passphrase store                       │
└────────────────────────────────────────────────────────────────────┘
                            │
┌────────────────────────────────────────────────────────────────────┐
│ SQLite (or SQLCipher-encrypted SQLite)                             │
│ + sentence-transformers (embedding model, lazy-loaded)             │
│ + hnswlib (optional, sidecar index files at <dbname>.ann/)         │
└────────────────────────────────────────────────────────────────────┘
```

## Memory tiers

```
short_term_memory   raw observations             TTL-based expiry
       ↓ (consolidation: cluster, summarize, promote)
midterm_memory      summarized experiences       confidence + decay
       ↓ (further promotion when confidence stays high over time)
long_term_memory    stable knowledge             periodic validation
```

Promotion is triggered by the **consolidation cycle** (manual or via
`run_consolidation_cycle`), which:

1. Clusters similar STM rows by cosine similarity (vectorized matmul,
   not pairwise)
2. Summarizes each cluster into a single MTM row via the configured LLM
3. Marks source STMs as `promoted` (soft delete, kept for audit)
4. Applies decay to MTM/LTM confidence based on time since last access
5. Detects contradictions and flags them in `contradictions` table
6. Boosts confidence on memories that survive multiple cycles
   (+0.05/cycle, capped at +0.3)

## Retrieval pipeline (the load-bearing piece)

`context.retrieve_context(conn, query, ...)` runs 9 stages:

```
0. Cache lookup        ── if a recent identical query is in query_cache, return it
1. Query embedding     ── sentence-transformers
2. Semantic search     ── ANN (hnswlib) or brute-force; per-tier
3. BM25 keyword        ── SQLite FTS5 over content
4. Graph traversal     ── walk relations from query-matched entities
5. Temporal weighting  ── exponential decay by age
6. Score fusion        ── 0.4×semantic + 0.25×bm25 + 0.2×graph + 0.15×temporal
7. Cross-encoder       ── (optional) re-rank top-N
8. Pinned injection    ── always-in-context memories prepended
9. Snapshot            ── record into context_snapshots for sleep-time analysis
```

Each query takes ~5-50 ms cold, <5 ms when cache-hit.

## Sleep cycle

Triggered automatically after `sleep_idle_threshold_seconds` of API
inactivity, or manually via `swadb maintenance sleep-cycle`. Phases:

1. **Consolidation** (above)
2. **ANN index rebuild** — all 6 tables, in parallel
3. **Query cache pre-compute** — identifies top-N frequent queries from
   recent `context_snapshots` and warms them
4. **Goal monitoring** — checks active goals against recent memories,
   emits `goal_match` notifications
5. **Graph pruning** — drops low-weight relations + orphan edges
6. **Custom alerts** — evaluates user-defined rules
7. **Cycle summary notification** — surfaces the run in the UI
8. **Webhook delivery** — POSTs the summary plus any backlog to the
   configured webhook URL

A typical cycle on a small DB takes 1-3 seconds; on a large DB with ANN
rebuild and pre-compute, 10-30 seconds.

## Auth model

Two API keys, both empty by default (open access on localhost):

- **`agent_api_key`** — required `X-API-Key` header for `/api/agent/*`
  routes (the surface AI agents use)
- **`operator_api_key`** — required `Authorization: Bearer` for `/api/*`
  operator routes (memory CRUD, settings, etc.)

Per-agent keys can override the global `agent_api_key` by storing
`{"api_key": "..."}` in `agents.config`.

## Concurrency model

- Single-threaded HTTP server (the stdlib `http.server.HTTPServer`)
  serves requests serially. Each request opens a fresh connection.
- Background workers use Python threads:
  - **Idle detector** — single thread monitoring last-call timestamp
  - **Scheduled task runner** — single thread polling
    `scheduled_tasks` table
  - **MCP server** — separate thread (or subprocess for stdio)
  - **File watcher** — single thread polling markdown inbox
  - **Webhook delivery** — daemon threads spawned per call (fire-and-forget)
- SQLite WAL mode allows multiple readers + one writer concurrently.
- The retrieval pipeline runs on the request thread; it's I/O-bound on
  the embedding model and DB lookups.

## Failure modes worth knowing

- **DB encrypted, no passphrase** → server starts in **locked mode**.
  Only `/api/encryption/unlock`, `/api/encryption/status`, and
  `/api/health` respond; everything else returns 423. UI shows an
  unlock screen.
- **Embedding model not yet warm** → first retrieval takes 1-3 seconds
  longer. Pre-warmup runs in background on `swadb serve` start.
- **MCP server crashes** → supervisor thread auto-restarts up to 5
  times in 60 seconds before giving up.
- **Query cache stale** → memory updates/deletes invalidate cache rows
  via SQLite `json_each`; sleep cycle drops rows older than
  `cache_ttl_hours`.
- **ANN index out of sync** → covered by hybrid mode (ANN results +
  brute-force tail over rows added since last rebuild).

## Where to dig in

- `swadb/context.py:retrieve_context` — the load-bearing function
- `swadb/consolidation.py:run_consolidation_cycle` — promotion logic
- `swadb/sleep.py:run_sleep_cycle` — the orchestrator
- `swadb/middleware.py` — LLM adapters + provider resolution
- `swadb/database.py` — connection and encryption plumbing
- `swadb/server.py` — HTTP routing
- `tests/test_*.py` — the contracts each module ships
