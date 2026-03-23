# AgentDB Development Guide

Setup, conventions, and workflow reference for contributors.

---

## Environment Setup

```bash
git clone https://github.com/your-org/AgentDB.git
cd AgentDB
python -m venv venv

# Windows
.\venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

The embedding model (`all-MiniLM-L6-v2`) downloads automatically on first use. Expect ~90 MB.

---

## Running

```bash
# Initialize a fresh database
python -m agentdb.cli init

# Start the server
python -m agentdb.cli serve

# Run with a specific database
python -m agentdb.cli --db dev.db init
python -m agentdb.cli --db dev.db serve --port 9000
```

---

## Project Layout

```
agentdb/
├── __init__.py          # Version string
├── schema.py            # DDL only. No runtime logic.
├── database.py          # Init, connection, seeding. Imports from schema.py.
├── crud.py              # Pure data access. Every function takes a connection.
├── embeddings.py        # Embedding model, similarity math. Stateless except model cache.
├── context.py           # Retrieval pipeline. Reads from crud.py + embeddings.py.
├── middleware.py         # LLM adapters. Calls context.py, crud.py, embeddings.py.
├── consolidation.py     # Background processing. Calls crud.py, embeddings.py.
├── markdown_parser.py   # Markdown → database pipeline. Calls crud.py, embeddings.py.
├── migration.py         # Chat import pipeline. Calls crud.py, embeddings.py.
├── server.py            # HTTP routing. Calls everything above.
├── cli.py               # Argparse CLI. Thin wrapper over database.py, crud.py, server.py.
└── static/
    └── index.html       # Single-file UI. No build step.
```

### Dependency Direction

```
cli.py ──→ server.py ──→ middleware.py ──→ context.py ──→ crud.py ──→ database.py ──→ schema.py
                    └──→ markdown_parser.py ──→ crud.py      └──→ embeddings.py
                    └──→ migration.py ──→ crud.py
                    └──→ consolidation.py ──→ crud.py
```

No circular imports. Every module depends only on modules below it in this chain.

---

## Code Conventions

### Python

- PEP 8 compliant.
- All SQL uses parameterized queries. Never format user input into SQL strings.
- Functions in `crud.py` accept `sqlite3.Connection` as the first argument and return plain dicts.
- JSON fields are serialized with `json.dumps()` on write and returned as raw strings on read (the caller decides whether to parse).
- UUIDs are generated with `uuid.uuid4()` as strings.
- Timestamps are UTC ISO format strings.

### HTML/JS

- Single file: `agentdb/static/index.html`.
- Inline CSS and vanilla ES6 JavaScript. No frameworks, no build tools, no CDN.
- Theme: white background, charcoal text, single teal (`#0d9488`) accent.
- All API calls go through the `api(method, path, body)` helper.
- HTML entity escaping via the `esc()` function for all user content.

### Database

- All integrity logic lives in SQLite triggers, not application code.
- `CREATE TABLE IF NOT EXISTS` for idempotent initialization.
- `INSERT OR IGNORE` for seeding to avoid duplicates on re-init.
- WAL mode for concurrent reads during writes.
- Foreign keys enabled via PRAGMA on every connection.

---

## Adding a New Table

1. Add the CREATE TABLE statement to `schema.py`.
2. Add it to the `ALL_TABLES` list in the correct position (respect foreign key ordering).
3. If it participates in polymorphic relations, add it to `CONTENT_TABLES`.
4. Add cascade delete triggers if needed.
5. Add indexes to `CREATE_INDEXES`.
6. Add the table name to `verify_schema()` in `database.py`.
7. Add CRUD functions to `crud.py`.
8. Add API endpoints to `server.py` (GET/POST/PUT/DELETE routes + handler methods).
9. Add UI support in `static/index.html`.
10. Update `docs/API_REFERENCE.md`.

---

## Adding a New LLM Provider

1. Create a new class in `middleware.py` that extends `ProviderAdapter`.
2. Implement `format_context(context_payload)` → string.
3. Implement `call_provider(messages, formatted_context, config)` → string.
4. Add the class to the `ADAPTERS` dict in `middleware.py`.
5. The provider becomes selectable via `meta_config` key `llm_provider`.

---

## Adding a New Markdown Document Type

1. Add the type string to the `valid_types` set in `parse_frontmatter()` in `markdown_parser.py`.
2. Add validation rules to `validate_frontmatter()`.
3. Create a `_process_{type}_document()` function.
4. Add the routing in `process_markdown_document()`.
5. Add reverse generation in `reverse_generate_markdown()` if applicable.
6. Update `docs/API_REFERENCE.md` and `README.md`.

---

## Adding a New Chat Import Provider

1. Create a `_parse_{provider}()` function in `migration.py`.
2. Add the provider to the dispatch in `_parse_export()`.
3. The function must return a list of session dicts, each with `title`, `started_at`, `ended_at`, and `messages` (list of `{role, content, timestamp}`).
4. Add the provider to the UI dropdown in `static/index.html`.

---

## Testing

Run the database initialization test:

```bash
python -m agentdb.cli init --force
python -m agentdb.cli verify
python -m agentdb.cli stats
```

Manual API smoke test:

```bash
# Start server
python -m agentdb.cli serve &

# Health check
curl http://127.0.0.1:8420/api/agent/health

# Create a memory
curl -X POST http://127.0.0.1:8420/api/memories/long \
  -H "Content-Type: application/json" \
  -d '{"content": "Test memory", "category": "fact"}'

# List memories
curl http://127.0.0.1:8420/api/memories/long

# Semantic search
curl -X POST http://127.0.0.1:8420/api/memories/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "tiers": ["long"]}'
```

---

## Database File

The `.db` file is the single source of truth. It contains:
- All 23 tables with data
- All triggers (referential integrity + cascade deletes)
- All configuration in `meta_config`
- All embeddings as BLOBs
- FTS5 virtual tables for keyword search

The file is fully portable. Copy it to any machine with Python 3.11+ and sentence-transformers installed, and it works.

---

## Implementation Phases

| Phase | Status | Description |
|-------|--------|-------------|
| 1. Foundation | Complete | Schema, CRUD, embeddings, CLI |
| 2. Agent Communication | Complete | Context retrieval, middleware, server, REST API |
| 3. Consolidation Engine | Complete | Promotion, decay, feedback processing |
| 4. Markdown Authoring | Complete | 4 doc types, file watcher, reverse generation |
| 5. Migration Pipeline | Complete | ChatGPT, Claude, JSONL parsers |
| 6. User Interface | Complete | Single-file HTML, full CRUD, all views |
| 7. Tauri Packaging | Not started | Desktop executable, sidecar management |
| 8. Workspace Awareness | Not started | File scanning, summarization |
| 9. Sleep-Time Processing | Not started | Reflection, graph pruning, notifications engine |
| 10. Encryption & Hardening | Not started | SQLCipher, reranker, performance tuning |
