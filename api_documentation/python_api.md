# Python API

For embedding swadb inside another Python application — no HTTP server
required. Most users won't need this; the CLI and HTTP API cover almost
every use case. But if you want to call into swadb directly, here's
the surface.

## What's stable

The "supported" Python API is fairly narrow:

- **Top-level convenience imports** (added in 0.1.1):
  `swadb.initialize_database`, `swadb.get_connection`,
  `swadb.verify_schema`, and the `swadb.crud` submodule. These are
  re-exports of the names below — use whichever form reads better.
- `swadb.database` — connection management, encryption helpers
- `swadb.crud` — synchronous CRUD over every table
- `swadb.context.retrieve_context` — the full retrieval pipeline
- `swadb.consolidation.run_consolidation_cycle` — promotion/decay/merge
- `swadb.sleep.run_sleep_cycle` — full sleep-time reflection
- `swadb.embeddings` — embedding generation + cosine similarity helpers
- `swadb.middleware.get_llm_config` / `get_adapter` — provider resolution
- `swadb.notifications` — webhook delivery helpers
- `swadb.system_access` — gated file r/w/list/stat + shell exec
- `swadb.ann.AnnIndexSet` — HNSW index management

Internal helpers (anything starting with `_`) and module-level globals
are not part of the supported surface and may change between minor
versions.

## Quick start: open a DB and read memories

```python
from swadb import initialize_database, get_connection, crud

# Fresh DB
conn = initialize_database("./swadb.db")

# Add memories
mid = crud.create_short_term_memory(
    conn,
    content="The user prefers Python over JavaScript.",
    source="conversation",
)

# List, search, update, delete
short = crud.list_short_term_memories(conn, limit=10)
got = crud.get_short_term_memory(conn, mid)
crud.update_short_term_memory(conn, mid, status="active")
crud.delete_short_term_memory(conn, mid)

conn.close()
```

For an existing DB, use `get_connection`:

```python
conn = get_connection("./swadb.db")
```

## Generating embeddings

```python
from swadb.embeddings import (
    generate_embedding, embedding_to_blob, blob_to_embedding,
    cosine_similarity, semantic_search,
)

vec = generate_embedding("hello world")          # numpy array (384,) float32
blob = embedding_to_blob(vec)                    # bytes for SQLite

# Cosine similarity between two vectors (or two BLOBs)
score = cosine_similarity(vec, other_vec)

# Top-K against a list of (id, blob) candidates
ranked = semantic_search(query_vec, candidates, top_k=10)
```

## Retrieving context

```python
from swadb.context import retrieve_context

payload = retrieve_context(
    conn,
    query="what does the user prefer?",
    agent_id="default",
    filters={"tier": ["short", "mid", "long"]},
)

# payload structure:
# {
#   "memories": {"short_term": [...], "midterm": [...], "long_term": [...]},
#   "pinned": [...],
#   "entities": [...],
#   "goals": [...],
#   "skills": [...],
#   "retrieval_strategies": ["semantic", "bm25", "graph", "temporal", "reranker"],
#   "snapshot_id": "...",
#   "from_cache": False
# }
```

## Working with entities and the knowledge graph

```python
alice = crud.create_entity(
    conn, canonical_name="alice", entity_type="person", aliases=["Alice"],
)
bob = crud.create_entity(conn, canonical_name="bob", entity_type="person")

# Link entities
rid = crud.create_relation(
    conn, alice, "entities", bob, "entities",
    edge_type="related_to", weight=0.7,
)

# Walk the graph from one entity
relations = crud.list_relations_for_node(conn, alice, "entities")
```

## Encryption

```python
from swadb.database import (
    encrypt_database, decrypt_database, rekey_database,
    is_db_encrypted,
    set_runtime_passphrase, clear_runtime_passphrase,
)

# Encrypt a plaintext DB
encrypt_database("./swadb.db", "my secret")
set_runtime_passphrase("my secret")    # in-memory; for the running process

# Now subsequent get_connection calls succeed without env var setup
conn = get_connection("./swadb.db")

# Rekey
rekey_database("./swadb.db", "my secret", "new secret")
set_runtime_passphrase("new secret")

# Decrypt back to plaintext
decrypt_database("./swadb.db", "new secret")
clear_runtime_passphrase()
```

`encrypt_database` keeps `<dbname>.preencrypt.bak` as a recovery file
until you delete it. `decrypt_database` keeps `<dbname>.predecrypt.bak`.

## LLM provider config

```python
from swadb.middleware import get_llm_config, get_adapter

cfg = get_llm_config(conn)
# {'llm_provider': 'claude', 'llm_model': 'claude-sonnet-4-6',
#  'llm_api_key': '...', 'llm_endpoint': '',
#  'context_window_tokens': 200000, ...}

adapter = get_adapter(cfg["llm_provider"])
response = adapter.call_provider(
    messages=[{"role": "user", "content": "hello"}],
    formatted_context="<system context here>",
    config=cfg,
)
```

`get_llm_config` returns `{}` when no provider is configured. Treat
that as "no LLM available."

## Running consolidation / sleep cycles manually

```python
from swadb.consolidation import run_consolidation_cycle
from swadb.sleep import run_sleep_cycle

# Consolidation only: STM -> MTM -> LTM, decay, contradiction detection
result = run_consolidation_cycle(conn)

# Full sleep: consolidation + ANN rebuild + query-cache pre-compute +
# goal monitoring + graph pruning + custom alerts + summary notification
result = run_sleep_cycle(conn)
```

These are blocking and can take seconds-to-minutes depending on the
size of the DB. The HTTP server runs them in background threads via
the idle detector.

## Local system access

```python
from swadb import crud
from swadb.system_access import (
    AccessDenied, read_file, write_file, list_dir, stat_path,
    execute_shell,
)

# Grant a directory
crud.create_file_access_grant(
    conn, directory_path="/srv/data", agent_id="default", permission="read",
)

# Read a file inside the grant
result = read_file(conn, agent_id="default", path="/srv/data/config.json")
# {'path': '/srv/data/config.json', 'size_bytes': 142, 'encoding': 'utf-8',
#  'content': '...'}

# Outside the grant -> AccessDenied
try:
    read_file(conn, "default", "/etc/passwd")
except AccessDenied:
    ...

# Shell exec — also requires shell_access_enabled=true config
crud.set_config(conn, "shell_access_enabled", "true")
result = execute_shell(
    conn, "default", "ls -la", working_dir="/srv/data",
    timeout_seconds=10,
)
# {'log_id': '...', 'exit_code': 0, 'stdout': '...', 'stderr': '',
#  'duration_ms': 23, 'timed_out': False, 'truncated': False}
```

## ANN index

```python
from swadb import ann

if ann.is_available():
    idx_set = ann.get_index_set("./swadb.db")
    summary = idx_set.load_or_build(conn)
    # {'loaded': 6, 'built': 0, 'skipped': 0}

    # Hybrid ANN + freshness search
    results = idx_set.search(
        conn, "short_term_memory", query_embedding, top_k=10,
        agent_filter=["default", "shared"],
        status_filter="active",
    )
    # [(id, similarity_score), ...]

    # Manual rebuild (e.g. after a bulk import)
    idx_set.rebuild_all(conn)
```

## Connection lifecycle

- **Open**: `get_connection(path)` returns either a plain `sqlite3.Connection`
  or a `sqlcipher3` connection depending on whether the file is
  encrypted. Both are drop-in compatible from your code's perspective.
- **Close**: standard `conn.close()`. swadb code closes connections
  per-request in the HTTP layer; if you're calling functions directly,
  manage the connection yourself.
- **Concurrency**: SQLite connections are not thread-safe. Use one
  connection per thread, or wrap access in a lock.

## What's NOT in the Python API

- The HTTP routing layer (`swadb.server.SwadbHandler`) is internal.
  Use the CLI's `serve` command or the public HTTP endpoints instead.
- The MCP server is similarly only meant to be invoked via `swadb mcp`.
- Module-level state (`_RUNTIME_PASSPHRASE`, `_GLOBAL_INDEX_SET`,
  cache hit counters) is not part of the contract; use the public
  setters/getters instead (`set_runtime_passphrase`, `get_index_set`,
  `cache_metrics`).
