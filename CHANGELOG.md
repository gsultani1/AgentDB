# Changelog

All notable changes to **swadb** are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-05-04

First public release on PyPI. The package is named `swadb`; the product
is branded **AgentDB**. Same software.

### Added — packaging
- `pyproject.toml` with PEP 621 metadata, `[project.scripts]` registering
  the `swadb` console command, and `[project.optional-dependencies]` for
  `[encryption]` (sqlcipher3), `[ann]` (hnswlib), `[all]`, and `[dev]`
  (pytest + build + twine).
- Apache 2.0 `LICENSE` file at repo root.
- `MANIFEST.in` defensively covers the source distribution (README, LICENSE,
  requirements*, pytest.ini, swadb/static/**).
- `swadb/__init__.py` exposes `__version__`, `__author__`, `__license__`,
  `__url__`.

### Added — features (everything new since the initial commit)
- **Sovereign agent memory core**: STM / midterm / long-term tiers with
  vectorized consolidation, contradiction detection, decay, and confidence
  boosting based on a survival reward (formula `+0.05/cycle`, capped at 0.3).
- **Demand-constructed context retrieval**: 9-stage pipeline combining
  semantic, BM25, graph traversal, temporal weighting, score fusion, and
  cross-encoder reranking.
- **ANN index** (HNSW via hnswlib, optional dep) with hybrid mode: ANN
  results from the index plus brute-force over rows added since last
  rebuild. Sub-millisecond search at 50k embeddings.
- **Query cache + sleep-time pre-computation**: top-N frequent queries
  identified from `context_snapshots` history are warmed during the sleep
  cycle; subsequent identical queries return in O(1). Invalidated on
  memory updates / deletes via SQLite `json_each`.
- **MCP server** with 9 tools (retrieve_context, ingest_memory,
  search_memories, list_memories, create_entity, list_entities,
  check_goals, get_health, run_consolidation), SSE + stdio transports,
  crash recovery with auto-restart.
- **HTTP server** with 60+ REST endpoints across operator, agent, and
  maintenance surfaces. Per-agent and operator API key auth.
- **Web UI** (single-page app served from the wheel) covering Dashboard,
  Memories with batch operations, Mind Map (canvas-based knowledge graph),
  Markdown editor, Skills, Entities, Chat with observability sidebar
  (context window meter, raw JSON mode), DB Console with AI query mode,
  Scheduler, MCP, Settings, Audit log, Feedback, Notifications.
- **Workspace scanning**: register codebase / project_folder / data_directory
  paths; the scanner indexes file metadata and embeds text/markdown/config
  contents. Per-row file count badges + per-tier breakdown.
- **SQLCipher encryption** end-to-end: enable/rekey/disable from the UI,
  in-memory passphrase store (no env var required after first unlock),
  unlock screen on encrypted-DB startup, atomic file swap with
  `.preencrypt.bak` and `.predecrypt.bak` recovery files. CLI fallback
  `swadb encryption disable --passphrase X` for terminal recovery.
- **Local system access** (file read/write/list/stat + shell execute)
  gated by `file_access_grants` rows. realpath-then-commonpath path
  resolution prevents symlink escape and substring-prefix neighbor bugs.
  Shell exec is opt-in (`shell_access_enabled=false` by default), with
  deny-keyword check, configurable timeout, and per-call audit logging.
- **Scheduled tasks**: interval-based runner for consolidation, sleep
  cycle, integrity check, workspace scan, custom notify actions.
- **Notification webhooks**: priority-threshold-gated POST delivery to a
  configurable URL, retry-on-failure semantics, fire-and-forget async
  helper for low-latency callers.
- **Skills**: 4 execution types (prompt template, Python sandbox, bash
  sandbox, MCP tool); resource-limited subprocess execution.
- **LLM provider registry**: 7 adapters (Claude / OpenAI / Ollama /
  llama.cpp / LM Studio / generic local / custom OpenAI-compat). Provider
  resolution chain: explicit id → agent default → active_provider_id →
  is_default → first is_active. The `llm_providers` table is the single
  source of truth.
- **File uploads**: multi-part chat messages with PDF / text / code / CSV
  extraction.
- **Conversation threads**: full CRUD, session linking, per-thread filters
  in retrieval.
- **Memory pinning**: pin/unpin with priority ordering; pinned memories
  always appear at the top of context payloads.
- **Markdown authoring**: 4 doc types (memory / instruction / skill /
  knowledge), reverse-generation back to markdown, hardened YAML
  frontmatter parser, optional Git knowledge sync.
- **Chat migration**: ChatGPT, Claude, JSONL formats with multi-part
  message support.
- **Entity detail drawer**: bundles memories referencing the entity,
  annotated relations, co-occurring entities (via two-stage `json_each`
  CTE), all in one round-trip; clickable from chat observability cards
  and mindmap canvas nodes.
- **Tauri desktop shell**: full Rust code with sidecar management and
  system tray.

### Added — testing
- `tests/` package with 79 pytest tests covering CRUD signatures,
  encryption lifecycle, query cache, ANN index, batch memory ops, system
  access boundaries, workspace lifecycle, DB query safety,
  notifications, entity detail aggregation. Auto-skip of encryption
  tests when sqlcipher3 isn't installed. ~23 seconds wall-clock for the
  fast suite.
- `pytest.ini` + `tests/conftest.py` with `fresh_db`,
  `reset_runtime_passphrase`, and `tmp_db_path` fixtures.
- `requirements-dev.txt` and `[dev]` extra in `pyproject.toml` register
  pytest + build + twine.

### Changed
- **Renamed Python package `agentdb` → `swadb`**. The `agentdb` name was
  taken on PyPI; `swadb` is unique. The product still presents as
  "AgentDB" in headings, window titles, and the JS namespace; only the
  module/CLI name changed.
- `SWADB_PASSPHRASE` is now the canonical env var for SQLCipher;
  `AGENTDB_PASSPHRASE` honored as a deprecated fallback with a one-shot
  warning.
- `swadb.db` is the default DB filename (was `agentdb.db`); the
  `<dbname>.ann/` sidecar dir is gitignored alongside it.
- `llm_providers` table is the single source of truth for provider
  config; flat `meta_config.llm_*` keys are no longer seeded on new DBs
  and the legacy `get_llm_config` fallback that read them was removed.
  Old DBs continue to receive write-only sync for backward compat with
  any external readers.
- DB Console safety: ATTACH / DETACH / DROP / ALTER are now ALWAYS
  blocked, even when `db_console_write_enabled=true`. Previously only
  the read-only mode rejected them.
- Dark mode CSS now has a real `[data-theme="light"]` override block, so
  clicking "Light" on a dark-OS machine actually switches.
- Chat sidebar toggle now lives in the chat header (in addition to the
  in-sidebar one), so hiding the sidebar no longer hides the way back.
- Encryption flow no longer requires server restart or env var setup —
  the running session continues seamlessly via an in-memory passphrase
  store; on next process start an Unlock screen accepts the passphrase
  via the UI.
- `datetime.utcnow()` and `datetime.utcfromtimestamp()` replaced with
  `datetime.now(timezone.utc).replace(tzinfo=None)` and equivalent
  across the codebase. Wire format unchanged (still naive ISO);
  silenced 1100+ deprecation warnings on Python 3.13+.

### Fixed
- All four `/api/memories/batch/*` handlers had a CRUD signature mismatch
  and would have crashed on first call (passed flat `ids` lists where
  `(id, table)` pairs were expected; passed `tag_name` where `tag_id`
  was expected; passed `source_table` where `from_tier` was expected).
- `POST /api/file-access-grants` had a positional-arg mismatch with the
  CRUD signature (same bug pattern).
- Recent Entities Quick Query referenced a column (`created_at`) that
  doesn't exist on the `entities` table (uses `first_seen`/`last_seen`).
- `crud.check_file_access` used `str.startswith` for grant-containment,
  meaning `/srv/dat` accidentally covered `/srv/data` (substring-prefix
  bug); replaced with `os.path.commonpath` after `os.path.realpath`.
- Provider type select in Settings only exposed 3 of 7 backend adapters;
  now lists all 7 with descriptive labels.
- Stale `agentdb.db` references in 5 JS recovery hints replaced with
  `swadb.db`.
- Context meter at 0% was invisible (4px transparent track); now has a
  visible border and 6px height with a min-width on the colored fill.

### Security
- Encrypted database files are detected via SQLite magic-header probe
  (not via attempted-open which can false-positive on lock contention).
- `get_connection` refuses to silently downgrade to plain SQLite when
  the file is encrypted but no passphrase is provided. Prior versions
  returned a broken connection that errored obscurely on first read.
- Shell exec gated by `shell_access_enabled` (off by default), passes
  through deny-keyword filter, working_dir must itself be inside a
  grant, output truncated at 5 MB, all calls logged to
  `shell_command_log`.

[Unreleased]: https://github.com/gsultani1/AgentDB/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/gsultani1/AgentDB/releases/tag/v0.1.0
