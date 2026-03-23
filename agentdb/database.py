"""
Database initialization and connection management for AgentDB.

Handles schema creation, trigger installation, WAL mode configuration,
default meta_config seeding, and optional SQLCipher encryption.

SQLCipher support
─────────────────
Install `sqlcipher3` (pip install sqlcipher3) or `pysqlcipher3` to enable
at-rest encryption.  The passphrase is read from the AGENTDB_PASSPHRASE
environment variable, or passed explicitly to get_connection().

When encryption_enabled = "true" in meta_config but no passphrase is
available, get_connection() falls back to plain SQLite and logs a warning.
"""

import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from agentdb.schema import ALL_TABLES, ALL_TRIGGERS, CREATE_INDEXES, CREATE_FTS_TABLES, FTS_SYNC_TRIGGERS


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
}


def get_connection(db_path, passphrase=None):
    """
    Open a connection to the AgentDB SQLite database.

    Args:
        db_path:    Path to the .db file (str or Path).
        passphrase: Optional encryption passphrase.  When None, the value of
                    the AGENTDB_PASSPHRASE environment variable is used.  If
                    neither is set, or if SQLCipher is not installed, a plain
                    SQLite connection is returned.

    Returns:
        sqlite3.Connection (or sqlcipher3 equivalent) with WAL mode and
        foreign keys enabled.
    """
    db_path = str(db_path)
    passphrase = passphrase or os.environ.get("AGENTDB_PASSPHRASE")

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
            "Warning: AGENTDB_PASSPHRASE is set but sqlcipher3 / pysqlcipher3 "
            "is not installed. Falling back to plain SQLite (data unencrypted)."
        )

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn


def encryption_status():
    """Return a dict describing the current SQLCipher availability."""
    return {
        "sqlcipher_available": _SQLCIPHER is not None,
        "passphrase_set": bool(os.environ.get("AGENTDB_PASSPHRASE")),
        "library": (
            "sqlcipher3" if _SQLCIPHER is not None else None
        ),
    }


def rekey_database(db_path, old_passphrase, new_passphrase):
    """
    Change the encryption passphrase on an existing SQLCipher database.

    Args:
        db_path:        Path to the encrypted .db file.
        old_passphrase: Current passphrase (or None for an unencrypted DB).
        new_passphrase: New passphrase (or None to decrypt).

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
        "views", "embeddings_cache",
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
