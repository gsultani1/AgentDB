"""
Command-line interface for AgentDB.

Provides commands for database initialization, schema verification,
configuration management, and manual memory operations.
"""

import argparse
import json
import sys
from pathlib import Path

from agentdb.database import initialize_database, get_connection, verify_schema, DEFAULT_CONFIG
from agentdb.schema import ALL_TABLES
from agentdb import crud


DEFAULT_DB_PATH = Path("agentdb.db")


def cmd_init(args):
    """Initialize a new AgentDB database."""
    db_path = Path(args.db)
    if db_path.exists() and not args.force:
        print(f"Database already exists at {db_path}. Use --force to reinitialize.")
        sys.exit(1)
    conn = initialize_database(db_path)
    result = verify_schema(conn)
    conn.close()
    if result["ok"]:
        print(f"Database initialized successfully at {db_path}")
        print(f"  Tables created: {len(ALL_TABLES)}")
        print(f"  Default config values: {len(DEFAULT_CONFIG)}")
    else:
        print(f"Schema verification failed. Missing tables: {result['missing']}")
        sys.exit(1)


def cmd_verify(args):
    """Verify database schema integrity."""
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        sys.exit(1)
    conn = get_connection(db_path)
    result = verify_schema(conn)
    conn.close()
    if result["ok"]:
        print(f"Schema verification passed. All {len(ALL_TABLES)} tables present.")
    else:
        print(f"Schema verification FAILED. Missing tables: {result['missing']}")
        sys.exit(1)


def cmd_config_list(args):
    """List all configuration values."""
    conn = get_connection(args.db)
    configs = crud.list_config(conn)
    conn.close()
    if not configs:
        print("No configuration values found.")
        return
    max_key_len = max(len(c["key"]) for c in configs)
    for c in configs:
        value_display = c["value"]
        if c["key"] in ("llm_api_key", "agent_api_key") and value_display:
            value_display = value_display[:4] + "****" if len(value_display) > 4 else "****"
        print(f"  {c['key']:<{max_key_len}}  {value_display}")


def cmd_config_get(args):
    """Get a single configuration value."""
    conn = get_connection(args.db)
    value = crud.get_config_value(conn, args.key)
    conn.close()
    if value is None:
        print(f"Config key '{args.key}' not found.")
        sys.exit(1)
    print(value)


def cmd_config_set(args):
    """Set a configuration value."""
    conn = get_connection(args.db)
    crud.set_config(conn, args.key, args.value)
    conn.close()
    print(f"Set {args.key} = {args.value}")


def cmd_stats(args):
    """Show database statistics."""
    conn = get_connection(args.db)
    tables = [
        ("short_term_memory", "Short-term memories"),
        ("midterm_memory", "Midterm memories"),
        ("long_term_memory", "Long-term memories"),
        ("skills", "Skills"),
        ("skill_implementations", "Skill implementations"),
        ("entities", "Entities"),
        ("goals", "Goals"),
        ("relations", "Relations"),
        ("tags", "Tags"),
        ("sessions", "Sessions"),
        ("contradictions", "Contradictions"),
        ("feedback", "Feedback entries"),
        ("audit_log", "Audit log entries"),
        ("context_snapshots", "Context snapshots"),
        ("workspaces", "Workspaces"),
        ("workspace_files", "Workspace files"),
        ("views", "Saved views"),
        ("embeddings_cache", "Cache entries"),
    ]
    print("AgentDB Statistics")
    print("=" * 40)
    for table, label in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {label:<25} {count:>6}")
    db_size = Path(args.db).stat().st_size
    print(f"\n  Database size: {db_size / 1024:.1f} KB")
    conn.close()


def cmd_memory_add(args):
    """Add a memory to short-term storage."""
    conn = get_connection(args.db)
    embedding = None
    if not args.no_embedding:
        try:
            from agentdb.embeddings import generate_embedding, embedding_to_blob
            embedding = embedding_to_blob(generate_embedding(args.content))
        except ImportError:
            print("Warning: sentence-transformers not available. Skipping embedding.")
    mid = crud.create_short_term_memory(
        conn, args.content, args.source, embedding=embedding,
        session_id=args.session,
    )
    conn.close()
    print(f"Created short-term memory: {mid}")


def cmd_memory_list(args):
    """List memories from a tier."""
    conn = get_connection(args.db)
    tier = args.tier
    if tier == "short":
        memories = crud.list_short_term_memories(conn, limit=args.limit)
    elif tier == "mid":
        memories = crud.list_midterm_memories(conn, limit=args.limit)
    elif tier == "long":
        memories = crud.list_long_term_memories(conn, limit=args.limit)
    else:
        print(f"Unknown tier: {tier}. Use 'short', 'mid', or 'long'.")
        sys.exit(1)
    conn.close()
    if not memories:
        print(f"No {tier}-term memories found.")
        return
    for m in memories:
        content_preview = m["content"][:80] + "..." if len(m["content"]) > 80 else m["content"]
        print(f"  [{m['id'][:8]}] {content_preview}")


def cmd_memory_search(args):
    """Semantic search across a memory tier."""
    try:
        from agentdb.embeddings import generate_embedding, semantic_search
    except ImportError:
        print("Error: sentence-transformers required for semantic search.")
        sys.exit(1)
    conn = get_connection(args.db)
    query_emb = generate_embedding(args.query)
    tier = args.tier
    table = {"short": "short_term_memory", "mid": "midterm_memory",
             "long": "long_term_memory"}[tier]
    rows = conn.execute(f"SELECT id, embedding FROM {table} WHERE embedding IS NOT NULL").fetchall()
    candidates = [(r["id"], r["embedding"]) for r in rows]
    results = semantic_search(query_emb, candidates, top_k=args.limit)
    for rid, score in results:
        row = conn.execute(f"SELECT content FROM {table} WHERE id = ?", (rid,)).fetchone()
        content_preview = row["content"][:80] + "..." if len(row["content"]) > 80 else row["content"]
        print(f"  [{rid[:8]}] {score:.4f}  {content_preview}")
    conn.close()


def cmd_entity_list(args):
    """List all entities."""
    conn = get_connection(args.db)
    entities = crud.list_entities(conn, entity_type=args.type, limit=args.limit)
    conn.close()
    if not entities:
        print("No entities found.")
        return
    for e in entities:
        print(f"  [{e['id'][:8]}] {e['entity_type']:<10} {e['canonical_name']}")


def cmd_session_start(args):
    """Start a new session."""
    conn = get_connection(args.db)
    sid = crud.create_session(conn)
    conn.close()
    print(f"Session started: {sid}")


def cmd_session_end(args):
    """End a session."""
    conn = get_connection(args.db)
    crud.end_session(conn, args.session_id, summary=args.summary)
    conn.close()
    print(f"Session ended: {args.session_id}")


def cmd_serve(args):
    """Start the AgentDB HTTP server."""
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found at {db_path}. Run 'agentdb init' first.")
        sys.exit(1)
    from agentdb.server import run_server
    run_server(str(db_path), host=args.host, port=args.port)


def build_parser():
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="agentdb",
        description="AgentDB - Sovereign Agent Memory System",
    )
    parser.add_argument(
        "--db", default=str(DEFAULT_DB_PATH),
        help=f"Path to the database file (default: {DEFAULT_DB_PATH})",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init
    p_init = subparsers.add_parser("init", help="Initialize a new database")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing database")

    # verify
    subparsers.add_parser("verify", help="Verify database schema")

    # config
    p_config = subparsers.add_parser("config", help="Configuration management")
    config_sub = p_config.add_subparsers(dest="config_command")
    config_sub.add_parser("list", help="List all configuration values")
    p_cfg_get = config_sub.add_parser("get", help="Get a configuration value")
    p_cfg_get.add_argument("key", help="Configuration key")
    p_cfg_set = config_sub.add_parser("set", help="Set a configuration value")
    p_cfg_set.add_argument("key", help="Configuration key")
    p_cfg_set.add_argument("value", help="Configuration value")

    # stats
    subparsers.add_parser("stats", help="Show database statistics")

    # memory
    p_memory = subparsers.add_parser("memory", help="Memory operations")
    mem_sub = p_memory.add_subparsers(dest="memory_command")
    p_mem_add = mem_sub.add_parser("add", help="Add a short-term memory")
    p_mem_add.add_argument("content", help="Memory content text")
    p_mem_add.add_argument("--source", default="conversation", help="Source channel")
    p_mem_add.add_argument("--session", help="Session ID")
    p_mem_add.add_argument("--no-embedding", action="store_true",
                           help="Skip embedding generation")
    p_mem_list = mem_sub.add_parser("list", help="List memories")
    p_mem_list.add_argument("tier", choices=["short", "mid", "long"], help="Memory tier")
    p_mem_list.add_argument("--limit", type=int, default=20, help="Max results")
    p_mem_search = mem_sub.add_parser("search", help="Semantic search")
    p_mem_search.add_argument("query", help="Search query text")
    p_mem_search.add_argument("--tier", choices=["short", "mid", "long"],
                              default="short", help="Memory tier to search")
    p_mem_search.add_argument("--limit", type=int, default=10, help="Max results")

    # entity
    p_entity = subparsers.add_parser("entity", help="Entity operations")
    ent_sub = p_entity.add_subparsers(dest="entity_command")
    p_ent_list = ent_sub.add_parser("list", help="List entities")
    p_ent_list.add_argument("--type", help="Filter by entity type")
    p_ent_list.add_argument("--limit", type=int, default=50, help="Max results")

    # session
    p_session = subparsers.add_parser("session", help="Session operations")
    sess_sub = p_session.add_subparsers(dest="session_command")
    sess_sub.add_parser("start", help="Start a new session")
    p_sess_end = sess_sub.add_parser("end", help="End a session")
    p_sess_end.add_argument("session_id", help="Session ID to end")
    p_sess_end.add_argument("--summary", help="Session summary text")

    # serve
    p_serve = subparsers.add_parser("serve", help="Start the HTTP server")
    p_serve.add_argument("--host", default="127.0.0.1", help="Bind address")
    p_serve.add_argument("--port", type=int, default=8420, help="Port number")

    return parser


def main():
    """Entry point for the AgentDB CLI."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    dispatch = {
        "init": cmd_init,
        "verify": cmd_verify,
        "stats": cmd_stats,
        "serve": cmd_serve,
    }

    if args.command in dispatch:
        dispatch[args.command](args)
    elif args.command == "config":
        config_dispatch = {
            "list": cmd_config_list,
            "get": cmd_config_get,
            "set": cmd_config_set,
        }
        if args.config_command in config_dispatch:
            config_dispatch[args.config_command](args)
        else:
            print("Usage: agentdb config {list|get|set}")
    elif args.command == "memory":
        mem_dispatch = {
            "add": cmd_memory_add,
            "list": cmd_memory_list,
            "search": cmd_memory_search,
        }
        if args.memory_command in mem_dispatch:
            mem_dispatch[args.memory_command](args)
        else:
            print("Usage: agentdb memory {add|list|search}")
    elif args.command == "entity":
        if args.entity_command == "list":
            cmd_entity_list(args)
        else:
            print("Usage: agentdb entity {list}")
    elif args.command == "session":
        sess_dispatch = {
            "start": cmd_session_start,
            "end": cmd_session_end,
        }
        if args.session_command in sess_dispatch:
            sess_dispatch[args.session_command](args)
        else:
            print("Usage: agentdb session {start|end}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
