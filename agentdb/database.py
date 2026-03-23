"""
Database initialization and connection management for AgentDB.

Handles schema creation, trigger installation, WAL mode configuration,
and default meta_config seeding.
"""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from agentdb.schema import ALL_TABLES, ALL_TRIGGERS, CREATE_INDEXES, CREATE_FTS_TABLES, FTS_SYNC_TRIGGERS


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
    "max_context_tokens": "4000",
    "consolidation_enabled": "true",
    "decay_enabled": "true",
    "markdown_inbox_path": "",
    "markdown_watch_enabled": "false",
    "markdown_watch_interval_seconds": "5",
    "sleep_idle_threshold_seconds": "300",
    "sleep_reflection_enabled": "true",
    "sleep_graph_pruning_threshold_days": "60",
    "notification_webhook_url": "",
    "notification_priority_threshold": "medium",
    "encryption_enabled": "false",
    "reranker_model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
    "reranker_enabled": "false",
    "bm25_enabled": "true",
    "graph_traversal_enabled": "true",
    "temporal_boost_enabled": "true",
    "temporal_decay_curve": "0.95",
}


def get_connection(db_path):
    """
    Open a connection to the AgentDB SQLite database.

    Args:
        db_path: Path to the .db file (str or Path).

    Returns:
        sqlite3.Connection with WAL mode and foreign keys enabled.
    """
    db_path = str(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn


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
        "feedback", "context_snapshots", "notification_queue",
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
