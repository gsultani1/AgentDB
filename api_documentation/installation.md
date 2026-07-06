# Installation

## Prerequisites

- **Python 3.10 or later** (tested through 3.13)
- A few hundred MB of disk for the embedding model (downloaded on first run)

## Standard install

```bash
pip install swadb
```

This gives you the core package: HTTP server, MCP server, CLI, web UI,
and the full memory pipeline using SQLite + sentence-transformers for
embeddings.

## Optional extras

swadb has two heavyweight features behind opt-in extras:

| Extra | Adds | Why you'd want it |
|---|---|---|
| `swadb[ann]` | `hnswlib>=0.8.0` | Sub-millisecond approximate nearest-neighbor search at >10k memories. Without it, semantic search uses brute-force cosine similarity (correct, just O(n) per query). |
| `swadb[encryption]` | `sqlcipher3>=0.5.0` | At-rest database encryption with passphrase-locked startup. Without it, the database is plain SQLite. |
| `swadb[all]` | both | If you want everything. |

```bash
pip install swadb[all]
```

Both extras gracefully degrade when absent — `swadb` still works without
them, just with the noted limitations.

## Development install

For contributing to swadb itself:

```bash
git clone https://github.com/gsultani1/AgentDB.git
cd AgentDB
pip install -e ".[dev]"
```

The `[dev]` extra adds `pytest>=8.0`, `build>=1.0`, and `twine>=5.0` for
running the test suite and building wheels.

## First run

```bash
swadb init                              # creates ./swadb.db
swadb verify                            # confirms 35 tables + 63 default config rows
swadb serve                             # starts HTTP on :8420 + MCP on :8421
```

Open http://127.0.0.1:8420 in a browser. You'll see the web UI
unauthenticated by default (no `agent_api_key` or `operator_api_key`
set yet — you can add those later in Settings).

## Custom database paths

Most commands accept `--db <path>`:

```bash
swadb --db /var/lib/swadb/main.db init
swadb --db /var/lib/swadb/main.db serve --port 9000
```

## Verifying the install

```bash
swadb --help
# usage: swadb [-h] [--db DB] {init,verify,config,stats,memory,entity,session,
#              serve,mcp,ann,cache,encryption} ...

python -c "import swadb; print(swadb.__version__)"
# 0.1.0
```

## Troubleshooting

- **Embedding model download is slow on first run** — sentence-transformers
  caches models in `~/.cache/huggingface` (or `%USERPROFILE%\.cache` on
  Windows). The default model `all-MiniLM-L6-v2` is ~80 MB.
- **`hnswlib` not installed but I want ANN** — install with
  `pip install swadb[ann]` or `pip install hnswlib`. swadb auto-detects
  it on next start.
- **`sqlcipher3` build error on Windows** — the wheels for `sqlcipher3`
  are limited; if the bare `pip install swadb[encryption]` fails on your
  platform, the encryption feature simply won't be available — the rest
  of swadb runs fine.
- **Port 8420 / 8421 already in use** — pass `--port` to `swadb serve`
  for the HTTP port; the MCP port is configurable in Settings via
  `meta_config.mcp_port`.
