"""MCP Server for AgentDB. Exposes capabilities as MCP tools."""
from mcp.server.fastmcp import FastMCP
from agentdb.database import get_connection
from agentdb import crud
from agentdb.context import retrieve_context
from agentdb.embeddings import generate_embedding, embedding_to_blob

mcp = FastMCP("AgentDB")
_db_path = None


def _get_conn():
    return get_connection(_db_path)


@mcp.tool()
def retrieve_context_tool(query: str, agent_id: str = "default") -> dict:
    """Retrieve semantically relevant context (memories, entities, goals, skills) for a query."""
    conn = _get_conn()
    try:
        result = retrieve_context(conn, query, agent_id=agent_id)
        # Strip binary embedding fields from results
        for tier in result.get("memories", {}).values():
            for m in tier:
                m.pop("embedding", None)
        return {"status": "ok", "data": result}
    finally:
        conn.close()


@mcp.tool()
def ingest_memory(content: str, source: str = "conversation", agent_id: str = "default") -> dict:
    """Store a new observation as a short-term memory."""
    conn = _get_conn()
    try:
        emb = embedding_to_blob(generate_embedding(content))
        mid = crud.create_short_term_memory(conn, content, source, embedding=emb, agent_id=agent_id)
        return {"status": "ok", "id": mid}
    finally:
        conn.close()


@mcp.tool()
def search_memories(query: str, tier: str = "short", limit: int = 10) -> dict:
    """Semantic search across a memory tier."""
    conn = _get_conn()
    try:
        from agentdb.embeddings import semantic_search, blob_to_embedding
        query_emb = generate_embedding(query)
        table_map = {"short": "short_term_memory", "mid": "midterm_memory", "long": "long_term_memory"}
        table = table_map.get(tier, "short_term_memory")
        rows = conn.execute(f"SELECT id, embedding FROM {table} WHERE embedding IS NOT NULL").fetchall()
        candidates = [(r[0], blob_to_embedding(r[1])) for r in rows if r[1]]
        results = semantic_search(query_emb, candidates, top_k=limit)
        memories = []
        for mid, score in results:
            row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (mid,)).fetchone()
            if row:
                m = dict(row)
                m.pop("embedding", None)
                m["similarity_score"] = round(score, 4)
                memories.append(m)
        return {"status": "ok", "data": memories}
    finally:
        conn.close()


@mcp.tool()
def list_memories(tier: str = "short", limit: int = 20) -> dict:
    """List memories by tier (short, mid, or long)."""
    conn = _get_conn()
    try:
        fn_map = {"short": crud.list_short_term_memories, "mid": crud.list_midterm_memories, "long": crud.list_long_term_memories}
        fn = fn_map.get(tier, crud.list_short_term_memories)
        memories = fn(conn, limit=limit)
        for m in memories:
            m.pop("embedding", None)
        return {"status": "ok", "data": memories}
    finally:
        conn.close()


@mcp.tool()
def create_entity(canonical_name: str, entity_type: str = "concept", aliases: str = "") -> dict:
    """Create a knowledge graph entity."""
    conn = _get_conn()
    try:
        alias_list = [a.strip() for a in aliases.split(",") if a.strip()] if aliases else []
        eid = crud.create_entity(conn, canonical_name, entity_type, aliases=alias_list)
        return {"status": "ok", "id": eid}
    finally:
        conn.close()


@mcp.tool()
def list_entities(entity_type: str = "", limit: int = 50) -> dict:
    """List entities in the knowledge graph."""
    conn = _get_conn()
    try:
        entities = crud.list_entities(conn, entity_type=entity_type or None, limit=limit)
        for e in entities:
            e.pop("embedding", None)
        return {"status": "ok", "data": entities}
    finally:
        conn.close()


@mcp.tool()
def check_goals(context: str) -> dict:
    """Check which active goals are relevant to the given context."""
    conn = _get_conn()
    try:
        from agentdb.embeddings import semantic_search, blob_to_embedding
        query_emb = generate_embedding(context)
        rows = conn.execute("SELECT id, embedding FROM goals WHERE status = 'active' AND embedding IS NOT NULL").fetchall()
        candidates = [(r[0], blob_to_embedding(r[1])) for r in rows if r[1]]
        results = semantic_search(query_emb, candidates, top_k=5)
        goals = []
        for gid, score in results:
            row = conn.execute("SELECT * FROM goals WHERE id = ?", (gid,)).fetchone()
            if row:
                g = dict(row)
                g.pop("embedding", None)
                g["relevance_score"] = round(score, 4)
                goals.append(g)
        return {"status": "ok", "data": goals}
    finally:
        conn.close()


@mcp.tool()
def get_health() -> dict:
    """Check AgentDB health status."""
    conn = _get_conn()
    try:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return {"status": "ok", "tables": len(tables), "database": _db_path}
    finally:
        conn.close()


@mcp.tool()
def run_consolidation() -> dict:
    """Trigger a memory consolidation cycle."""
    from agentdb.consolidation import run_consolidation_cycle
    conn = _get_conn()
    try:
        return run_consolidation_cycle(conn)
    finally:
        conn.close()


def run_mcp_server(db_path, transport="stdio", host="127.0.0.1", port=8421):
    """Start the MCP server. Called directly for stdio mode or in a daemon thread for sse."""
    global _db_path
    _db_path = db_path
    if transport == "sse":
        # FastMCP SSE runs its own uvicorn server; configure host/port via settings if supported
        try:
            mcp.settings.host = host
            mcp.settings.port = port
        except AttributeError:
            pass  # older FastMCP versions don't expose settings
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")
