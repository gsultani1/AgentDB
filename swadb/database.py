"""
Database initialization and connection management for AgentDB.

Handles schema creation, trigger installation, WAL mode configuration,
default meta_config seeding, and optional SQLCipher encryption.

SQLCipher support
─────────────────
Install `sqlcipher3` (pip install sqlcipher3) or `pysqlcipher3` to enable
at-rest encryption.  The passphrase is read from the SWADB_PASSPHRASE
environment variable (with AGENTDB_PASSPHRASE accepted as a deprecated
fallback during the rename transition), or passed explicitly to
get_connection().

When encryption_enabled = "true" in meta_config but no passphrase is
available, get_connection() falls back to plain SQLite and logs a warning.
"""

import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from swadb.schema import ALL_TABLES, ALL_TRIGGERS, CREATE_INDEXES, CREATE_FTS_TABLES, FTS_SYNC_TRIGGERS


# ── SQLCipher detection ───────────────────────────────────────────────────────

def _try_import_sqlcipher():
    """Return the sqlcipher sqlite3-compatible module, or None if unavailable."""
    try:
        from sqlcipher3 import dbapi2 as sqlcipher
        return sqlcipher
    except ImportError:
        pass
    try:
        from pysqlcipher3 import dbapi2 as sqlcipher
        return sqlcipher
    except ImportError:
        pass
    return None


_SQLCIPHER = _try_import_sqlcipher()


DEFAULT_CONFIG = {
    "embedding_model": "all-MiniLM-L6-v2",
    "embedding_dimensions": "384",
    "consolidation_interval_seconds": "300",
    "decay_rate_multiplier": "1.0",
    "stm_default_ttl_seconds": "3600",
    "promotion_confidence_threshold": "0.8",
    "clustering_similarity_threshold": "0.85",
    "context_results_per_tier": "10",
    "goal_similarity_threshold": "0.7",
    "skill_similarity_threshold": "0.6",
    "orphan_handling_mode": "flag",
    "staleness_threshold_days": "90",
    "llm_provider": "claude",
    "llm_api_key": "",
    "llm_model": "claude-sonnet-4-20250514",
    "llm_endpoint": "",
    "agent_api_key": "",
    "operator_api_key": "",
    "max_context_tokens": "4000",
    "consolidation_enabled": "true",
    "decay_enabled": "true",
    "markdown_inbox_path": "",
    "markdown_watch_enabled": "false",
    "markdown_watch_interval_seconds": "5",
    "sleep_idle_threshold_seconds": "300",
    "sleep_reflection_enabled": "true",
    "sleep_graph_pruning_threshold_days": "60",
    "sleep_goal_monitor_window_hours": "24",
    "min_relation_weight": "0.05",
    "notification_webhook_url": "",
    "notification_priority_threshold": "medium",
    "encryption_enabled": "false",
    "reranker_model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
    "reranker_enabled": "false",
    "bm25_enabled": "true",
    "graph_traversal_enabled": "true",
    "temporal_boost_enabled": "true",
    "temporal_decay_curve": "0.95",
    "scheduler_enabled": "true",
    "scheduler_poll_interval_seconds": "5",
    "mcp_enabled": "true",
    "mcp_transport": "sse",
    "mcp_port": "8421",
    "db_console_write_enabled": "false",
    # v1.5 additions
    "active_provider_id": "",
    "reranker_candidates": "20",
    "cache_ttl_hours": "24",
    "max_file_context_tokens": "2000",
    "db_query_timeout_seconds": "5",
    "skill_timeout_seconds": "30",
    "skill_max_memory_mb": "256",
    "skill_allow_network": "false",
    "knowledge_git_repo": "",
    "knowledge_git_branch": "main",
    "knowledge_git_auto_commit": "false",
    "last_git_sync_commit": "",
    "last_git_sync_at": "",
    "custom_alert_rules": "[]",
    "theme_preference": "auto",
    # ANN (approximate-nearest-neighbor) index — sidecar HNSW indexes per
    # embedding-bearing table, rebuilt after each consolidation cycle.
    # When disabled or hnswlib is missing, retrieval falls back to brute-force.
    "ann_index_enabled": "true",
    "ann_rebuild_strategy": "after_consolidation",
    # Sleep-time query pre-computation — sleep cycle picks the top-N most
    # frequent queries from context_snapshots history, runs the full
    # retrieval pipeline, and stashes results in query_cache. Subsequent
    # identical queries get an O(1) lookup (subject to cache_ttl_hours).
    "sleep_pre_compute_enabled": "true",
    "sleep_pre_compute_top_n": "10",
}


def _read_passphrase_env():
    """
    Read the encryption passphrase from the environment.

    SWADB_PASSPHRASE is canonical. AGENTDB_PASSPHRASE is honored as a
    deprecated fallback so existing encrypted databases continue to open
    after the package rename; a one-shot warning is printed in that case.
    """
    val = os.environ.get("SWADB_PASSPHRASE")
    if val:
        return val
    legacy = os.environ.get("AGENTDB_PASSPHRASE")
    if legacy:
        if not getattr(_read_passphrase_env, "_warned", False):
            print(
                "Warning: AGENTDB_PASSPHRASE is deprecated; rename it to "
                "SWADB_PASSPHRASE. The legacy variable will stop being read "
                "in a future release."
            )
            _read_passphrase_env._warned = True
        return legacy
    return None


def get_connection(db_path, passphrase=None):
    """
    Open a connection to the AgentDB SQLite database.

    Args:
        db_path:    Path to the .db file (str or Path).
        passphrase: Optional encryption passphrase. When None, the value of
                    the SWADB_PASSPHRASE environment variable is used (with
                    AGENTDB_PASSPHRASE accepted as a deprecated fallback).
                    If neither is set, or if SQLCipher is not installed, a
                    plain SQLite connection is returned.

    Returns:
        sqlite3.Connection (or sqlcipher3 equivalent) with WAL mode and
        foreign keys enabled.
    """
    db_path = str(db_path)
    passphrase = passphrase or _read_passphrase_env()

    # Refuse to silently downgrade if the file on disk is encrypted but we
    # have no passphrase. Otherwise we'd return a plain sqlite3 connection
    # whose first read would error obscurely deep in the request path.
    if passphrase is None and is_db_encrypted(db_path):
        raise RuntimeError(
            f"Database at {db_path} is encrypted but no passphrase was provided. "
            "Set SWADB_PASSPHRASE in the environment or pass passphrase= explicitly."
        )

    if passphrase and _SQLCIPHER is not None:
        conn = _SQLCIPHER.connect(db_path)
        # PRAGMA key must be the very first statement on an encrypted database
        conn.execute(f"PRAGMA key = '{passphrase}';")
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.row_factory = _SQLCIPHER.Row
        return conn

    if passphrase and _SQLCIPHER is None:
        print(
            "Warning: encryption passphrase is set but sqlcipher3 / pysqlcipher3 "
            "is not installed. Falling back to plain SQLite (data unencrypted)."
        )

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn


def is_db_encrypted(db_path):
    """
    Detect whether a .db file is encrypted by attempting a plain-SQLite open.

    Encrypted SQLCipher databases have an encrypted page header, so plain
    SQLite errors with "file is not a database" on any read. Returns False
    if the file doesn't exist (a not-yet-created DB is "not encrypted").
    """
    db_path = str(db_path)
    if not Path(db_path).exists():
        return False
    try:
        probe = sqlite3.connect(db_path)
        try:
            probe.execute("SELECT 1 FROM sqlite_master LIMIT 1")
            return False  # readable as plain SQLite
        finally:
            probe.close()
    except sqlite3.DatabaseError:
        return True


def encryption_status(db_path=None):
    """
    Return a dict describing encryption library availability and (optionally)
    whether a specific database file is currently encrypted.
    """
    out = {
        "sqlcipher_available": _SQLCIPHER is not None,
        "passphrase_set": bool(_read_passphrase_env()),
        "library": "sqlcipher3" if _SQLCIPHER is not None else None,
        "encryption_enabled_config": None,  # caller can fill from meta_config
    }
    if db_path is not None:
        out["db_path"] = str(db_path)
        out["db_encrypted"] = is_db_encrypted(db_path)
    return out


def rekey_database(db_path, old_passphrase, new_passphrase):
    """
    Change the encryption passphrase on an already-encrypted SQLCipher database.

    Args:
        db_path:        Path to the encrypted .db file.
        old_passphrase: Current passphrase.
        new_passphrase: New passphrase (or empty/None to also decrypt — though
                        encrypt_database/decrypt_database are clearer choices
                        for that direction).

    Raises:
        RuntimeError if SQLCipher is not available.
    """
    if _SQLCIPHER is None:
        raise RuntimeError(
            "sqlcipher3 or pysqlcipher3 must be installed to use rekey_database."
        )
    conn = get_connection(db_path, passphrase=old_passphrase)
    if new_passphrase:
        conn.execute(f"PRAGMA rekey = '{new_passphrase}';")
    else:
        conn.execute("PRAGMA rekey = '';")
    conn.close()


def encrypt_database(db_path, passphrase):
    """
    Convert a plaintext SQLite database to a SQLCipher-encrypted one.

    Uses SQLCipher's `sqlcipher_export` to copy every page into a fresh
    encrypted file, then atomically swaps the original. The original is
    preserved with a `.preencrypt.bak` suffix until the swap succeeds, so a
    crash mid-operation leaves the DB recoverable.

    Caller must ensure no other process has the DB open. The server should
    be restarted after this returns so the in-process connection picks up
    the encrypted file.

    Raises:
        RuntimeError if SQLCipher is not available.
        FileNotFoundError if db_path does not exist.
        ValueError if the DB is already encrypted.
    """
    if _SQLCIPHER is None:
        raise RuntimeError(
            "sqlcipher3 or pysqlcipher3 must be installed to use encrypt_database."
        )
    if not passphrase:
        raise ValueError("passphrase must be a non-empty string")
    src = Path(db_path)
    if not src.exists():
        raise FileNotFoundError(f"database not found: {db_path}")
    if is_db_encrypted(src):
        raise ValueError(f"database at {db_path} is already encrypted; use rekey instead")

    # 1) Build a fresh encrypted DB next to the source.
    tmp = src.with_suffix(src.suffix + ".encrypted.tmp")
    if tmp.exists():
        tmp.unlink()

    plain = sqlite3.connect(str(src))
    try:
        # The ATTACH + sqlcipher_export pattern has to run from a SQLCipher
        # connection so that the cryptographic page handler is active for
        # the attached side. Open the source via SQLCipher (no key set; an
        # unkeyed SQLCipher connection reads plaintext SQLite fine).
        bridge = _SQLCIPHER.connect(str(src))
        try:
            bridge.execute(f"ATTACH DATABASE '{tmp}' AS encrypted KEY '{passphrase}';")
            bridge.execute("SELECT sqlcipher_export('encrypted');")
            bridge.execute("DETACH DATABASE encrypted;")
            bridge.commit()
        finally:
            bridge.close()
    finally:
        plain.close()

    # 2) Atomically swap. Keep the plain DB as a backup until success.
    backup = src.with_suffix(src.suffix + ".preencrypt.bak")
    if backup.exists():
        backup.unlink()
    src.rename(backup)
    try:
        tmp.rename(src)
    except Exception:
        # Restore on failure
        backup.rename(src)
        raise
    # Success — keep .preencrypt.bak for one cycle so the user can restore
    # if their passphrase is wrong; a follow-up `verify` flow can prune it.


def decrypt_database(db_path, passphrase):
    """
    Inverse of encrypt_database: produce a plaintext SQLite copy from an
    encrypted DB and atomically swap. The encrypted original is kept as
    `.predecrypt.bak` until the swap succeeds.

    Raises:
        RuntimeError if SQLCipher is not available.
        FileNotFoundError if db_path does not exist.
        ValueError if the DB is not currently encrypted.
    """
    if _SQLCIPHER is None:
        raise RuntimeError(
            "sqlcipher3 or pysqlcipher3 must be installed to use decrypt_database."
        )
    if not passphrase:
        raise ValueError("passphrase must be a non-empty string")
    src = Path(db_path)
    if not src.exists():
        raise FileNotFoundError(f"database not found: {db_path}")
    if not is_db_encrypted(src):
        raise ValueError(f"database at {db_path} is not encrypted; nothing to decrypt")

    tmp = src.with_suffix(src.suffix + ".plain.tmp")
    if tmp.exists():
        tmp.unlink()

    bridge = _SQLCIPHER.connect(str(src))
    try:
        bridge.execute(f"PRAGMA key = '{passphrase}';")
        # Probe that the key works before doing anything destructive
        try:
            bridge.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except Exception as e:
            raise ValueError(f"passphrase did not unlock the database: {e}")
        bridge.execute(f"ATTACH DATABASE '{tmp}' AS plaintext KEY '';")
        bridge.execute("SELECT sqlcipher_export('plaintext');")
        bridge.execute("DETACH DATABASE plaintext;")
        bridge.commit()
    finally:
        bridge.close()

    backup = src.with_suffix(src.suffix + ".predecrypt.bak")
    if backup.exists():
        backup.unlink()
    src.rename(backup)
    try:
        tmp.rename(src)
    except Exception:
        backup.rename(src)
        raise


def initialize_database(db_path):
    """
    Create all tables, triggers, indexes, and seed default config.

    Args:
        db_path: Path to the .db file. Created if it doesn't exist.

    Returns:
        sqlite3.Connection to the initialized database.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Create all tables
    for ddl in ALL_TABLES:
        cursor.executescript(ddl)

    # Create all indexes
    for idx in CREATE_INDEXES:
        cursor.execute(idx)

    # Create all triggers
    for trigger in ALL_TRIGGERS:
        cursor.executescript(trigger)

    # Create FTS5 virtual tables for BM25 search
    for fts in CREATE_FTS_TABLES:
        try:
            cursor.execute(fts)
        except Exception:
            pass  # FTS5 may not be available on all SQLite builds

    # Create FTS5 sync triggers for automatic index maintenance
    for trigger in FTS_SYNC_TRIGGERS:
        try:
            cursor.execute(trigger)
        except Exception:
            pass  # FTS5 may not be available on all SQLite builds

    # Backfill FTS tables for any pre-existing rows (safe to run on fresh or upgraded DBs)
    for base_table, fts_table in [
        ("short_term_memory", "stm_fts"),
        ("midterm_memory", "mtm_fts"),
        ("long_term_memory", "ltm_fts"),
    ]:
        try:
            fts_count = cursor.execute(f"SELECT COUNT(*) FROM {fts_table}").fetchone()[0]
            base_count = cursor.execute(f"SELECT COUNT(*) FROM {base_table}").fetchone()[0]
            if fts_count < base_count:
                cursor.execute(
                    f"INSERT INTO {fts_table}(rowid, content) "
                    f"SELECT rowid, content FROM {base_table}"
                )
        except Exception:
            pass  # FTS5 not available

    # Seed default configuration
    _seed_default_config(cursor)

    # Seed default agent
    _seed_default_agent(cursor)

    conn.commit()
    return conn


def _seed_default_config(cursor):
    """Insert default meta_config values if they don't already exist."""
    now = datetime.utcnow().isoformat()
    for key, value in DEFAULT_CONFIG.items():
        cursor.execute(
            """
            INSERT OR IGNORE INTO meta_config (id, key, value, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), key, value, now),
        )


def _seed_default_agent(cursor):
    """Insert the default agent if it doesn't already exist."""
    now = datetime.utcnow().isoformat()
    cursor.execute(
        """
        INSERT OR IGNORE INTO agents (id, name, description, created_at)
        VALUES ('default', 'Default Agent', 'Single-agent default instance', ?)
        """,
        (now,),
    )


def verify_schema(conn):
    """
    Verify that all expected tables exist in the database.

    Args:
        conn: sqlite3.Connection

    Returns:
        dict with 'ok' bool and 'missing' list of missing table names.
    """
    expected_tables = [
        "agents", "short_term_memory", "midterm_memory", "long_term_memory",
        "skills", "skill_implementations", "relations", "entities",
        "goals", "tags", "tag_assignments", "workspaces", "workspace_files",
        "sessions", "meta_config", "contradictions", "audit_log",
        "feedback", "context_snapshots", "notification_queue", "scheduled_tasks",
        "views", "query_cache", "llm_providers",
        # v1.5 tables
        "conversation_threads", "pinned_memories", "file_attachments",
        "skill_executions", "channel_configs", "channel_messages",
        "autonomous_tasks", "task_steps", "task_actions",
        "file_access_grants", "shell_command_log",
    ]
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    existing = {row[0] for row in cursor.fetchall()}
    missing = [t for t in expected_tables if t not in existing]
    return {"ok": len(missing) == 0, "missing": missing}


def backfill_fts_tables(conn):
    """Populate FTS5 tables from existing memory data."""
    for table, fts in [("short_term_memory", "stm_fts"), ("midterm_memory", "mtm_fts"), ("long_term_memory", "ltm_fts")]:
        conn.execute(f"DELETE FROM {fts}")
        conn.execute(f"INSERT INTO {fts}(rowid, content) SELECT rowid, content FROM {table}")
    conn.commit()
