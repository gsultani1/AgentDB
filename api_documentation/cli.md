# CLI Reference

After `pip install swadb`, the `swadb` command is on your PATH.
Equivalent to `python -m swadb.cli`.

```
swadb [--db PATH] <subcommand> [args]
```

The `--db PATH` flag goes BEFORE the subcommand and defaults to
`swadb.db` in the current directory.

## Subcommand index

| Command | Purpose |
|---|---|
| [`init`](#init) | Create a new database |
| [`verify`](#verify) | Check schema integrity |
| [`stats`](#stats) | Row counts per table |
| [`config {list,get,set}`](#config) | Read or update `meta_config` rows |
| [`memory {add,list,search}`](#memory) | Memory CRUD without the server |
| [`entity {list}`](#entity) | List knowledge-graph entities |
| [`session {start,end}`](#session) | Manage conversation sessions |
| [`serve`](#serve) | Start the HTTP server |
| [`mcp`](#mcp) | Start the MCP server (stdio or SSE) |
| [`ann {rebuild,status}`](#ann) | Manage HNSW indexes |
| [`cache {stats,clear}`](#cache) | Query-cache ops |
| [`encryption {status,enable,disable,rekey}`](#encryption) | Offline encryption management — works when locked out of the UI |

## init

```bash
swadb init
swadb --db custom.db init
swadb init --force            # overwrites an existing DB at the path
```

Creates the file with all 35 tables, indexes, FTS5 virtual tables,
triggers, default `meta_config` rows, and a default agent.

## verify

```bash
swadb verify
```

Confirms every expected table exists. Useful after manual schema edits
or upgrades.

## stats

```bash
swadb stats
```

Prints row counts for every table. Roughly the same data the
`/api/stats` endpoint returns.

## config

```bash
swadb config list                                  # all key/value pairs
swadb config get embedding_model                   # one key
swadb config set consolidation_interval_seconds 600
```

Every meta_config key is documented in [configuration.md](configuration.md).

## memory

```bash
swadb memory add "the user prefers Python" --source conversation
swadb memory list short --limit 20
swadb memory search "python" --tier short --limit 5
```

`tier` is one of `short`, `mid`, `long`.

## entity

```bash
swadb entity list                  # all entities
swadb entity list --type person    # filtered
swadb entity list --limit 100
```

## session

```bash
SESSION_ID=$(swadb session start | tail -1)
# ... use the agent ...
swadb session end $SESSION_ID --summary "discussed architecture"
```

## serve

```bash
swadb serve                            # binds 127.0.0.1:8420
swadb serve --host 0.0.0.0 --port 9000
```

Starts the HTTP server. By default also auto-starts the MCP server on
port 8421 (SSE transport) — that's controlled by `mcp_enabled` and
`mcp_port` in `meta_config`.

If the database is encrypted and no passphrase is available
(`SWADB_PASSPHRASE` env var unset, no in-memory passphrase), the
server starts in **locked mode** — only the unlock screen and a few
status endpoints respond. Open the web UI to enter the passphrase.

## mcp

```bash
swadb mcp                              # stdio transport (for Claude Desktop, etc.)
swadb mcp --transport sse --port 8421  # SSE transport
```

See [mcp.md](mcp.md) for the 9 tools exposed and configuration examples
for popular clients.

## ann

```bash
swadb ann status                       # show per-table index counts + last_built_at
swadb ann rebuild                      # rebuild all indexes from current DB state
```

ANN indexes auto-rebuild after each consolidation cycle in normal
operation. Manual rebuild is useful after bulk imports.

## cache

```bash
swadb cache stats                      # row count, total hits, oldest entry
swadb cache clear                      # drop all cached query results
```

## encryption

```bash
swadb encryption status                                          # offline check
swadb encryption enable --passphrase 'my secret'                 # plaintext -> encrypted
swadb encryption disable --passphrase 'my secret'                # encrypted -> plaintext
swadb encryption rekey --old-passphrase OLD --new-passphrase NEW # change passphrase
```

These commands work **without a running server** and are the recovery
path if you've encrypted the DB and forgotten to start the server with
the right passphrase. See `enable` and `disable` for the full workflow.

The recommended path for normal operation is the in-UI Settings →
Encryption flow — the running server stores the passphrase in process
memory after one successful unlock.
