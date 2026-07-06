# swadb API Documentation

This folder contains the user-facing reference for **swadb 0.1.0**. It's
the documentation that ships alongside the PyPI release and answers
"how do I use this once it's installed?"

| Doc | Audience | Reads in |
|---|---|---|
| [installation.md](installation.md) | Anyone trying it out | 3 min |
| [cli.md](cli.md) | Operators running `swadb` from a terminal | 10 min |
| [http_api.md](http_api.md) | Anyone integrating via HTTP | 15 min |
| [python_api.md](python_api.md) | Anyone embedding swadb as a library | 10 min |
| [mcp.md](mcp.md) | Anyone wiring swadb into an MCP-aware client (Claude Desktop, Cursor, etc.) | 5 min |
| [configuration.md](configuration.md) | Anyone tuning behavior via `meta_config` | reference |
| [extras.md](extras.md) | Anyone deciding which optional dependencies to install | 2 min |
| [troubleshooting.md](troubleshooting.md) | Anyone staring at an error message | 5 min |
| [architecture.md](architecture.md) | Anyone wanting the 30k-foot system view | 10 min |

For schema-level details (every table, every column), see the
existing `docs/SCHEMA_REFERENCE.md` in the repo root.

## Quick orientation

swadb is **a self-contained agent memory system**. One Python package
provides:

- **A single SQLite database file** (`swadb.db` by default) with 35
  tables for tiered memory, knowledge graph, sessions, audit log, and
  configuration.
- **An HTTP server** (`swadb serve`, port 8420) with a built-in web UI
  and 60+ REST endpoints.
- **An MCP server** (`swadb mcp`, SSE port 8421) exposing 9 tools to
  any MCP-aware client.
- **A CLI** (`swadb <subcommand>`) for ops without spinning up the server.
- **A Python API** (`from swadb import crud, ...`) for embedding swadb
  inside other Python applications.

The product and the PyPI package share one name: **swadb** (formerly
branded AgentDB — the GitHub repository URL still reflects the old name).

## Conventions

- Code blocks marked `bash` work on macOS, Linux, and Windows (with
  `bash` available, e.g. Git Bash). Pure-Windows equivalents are noted
  where they differ.
- HTTP examples use `curl`. Replace `localhost:8420` with your server's
  address if running remotely.
- The `swadb` shell command and `python -m swadb.cli` are equivalent.
  All examples use the shorter form; both work.
