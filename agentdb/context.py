"""
Context retrieval pipeline for AgentDB.

Implements the multi-stage retrieval pipeline described in PRD Section 6.2:
1. Generate embedding from query text
2. Cosine similarity search across all three memory tiers
3. Entity identification and expansion via relations
4. Goal matching against active goal embeddings
5. Skill matching against skill description embeddings

Returns a unified context payload with labeled sections.
"""

import json
from datetime import datetime

from agentdb import crud
from agentdb.embeddings import (
    generate_embedding,
    embedding_to_blob,
    blob_to_embedding,
    cosine_similarity,
    semantic_search,
)


def retrieve_context(conn, query, filters=None, config=None, agent_id=None):
    """
    Execute the full multi-strategy context retrieval pipeline.

    Args:
        conn: sqlite3.Connection
        query: str, the query text to search against.
        filters: dict with optional keys:
            - tier: list of tiers to search (default all)
            - entity: entity name or ID filter
            - tags: list of tag names
            - time_range: dict with 'start' and 'end' ISO timestamps
            - confidence_min: float minimum confidence
        config: dict of meta_config overrides (uses DB defaults if None)
        agent_id: str, scope retrieval to this agent + 'shared' memories.

    Returns:
        dict with keys: memories, entities, goals, skills, retrieval_strategies
    """
    if filters is None:
        filters = {}
    if config is None:
        config = _load_retrieval_config(conn)

    top_k = int(config.get("context_results_per_tier", 10))
    goal_threshold = float(config.get("goal_similarity_threshold", 0.7))
    skill_threshold = float(config.get("skill_similarity_threshold", 0.6))
    bm25_enabled = config.get("bm25_enabled", "true") == "true"
    graph_enabled = config.get("graph_traversal_enabled", "true") == "true"
    temporal_enabled = config.get("temporal_boost_enabled", "true") == "true"
    temporal_curve = float(config.get("temporal_decay_curve", "0.95"))

    strategies_used = ["semantic"]

    # Stage 1: Generate query embedding
    query_embedding = generate_embedding(query)

    # Stage 2: Multi-tier semantic search
    tiers_to_search = filters.get("tier", ["short", "mid", "long"])
    all_results = {}  # id -> {entry, scores}

    tier_map = {
        "short": ("short_term_memory", "short_term"),
        "mid": ("midterm_memory", "midterm"),
        "long": ("long_term_memory", "long_term"),
    }

    for tier_key, (table, label) in tier_map.items():
        if tier_key not in tiers_to_search:
            continue
        candidates = _get_memory_candidates(conn, table, filters, agent_id=agent_id)
        results = semantic_search(query_embedding, candidates, top_k=top_k * 2)
        for mid, score in results:
            row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (mid,)).fetchone()
            if row:
                entry = dict(row)
                entry["tier"] = label
                entry.pop("embedding", None)
                all_results[mid] = {"entry": entry, "semantic": score, "bm25": 0.0, "graph": 0.0, "temporal": 0.0}

    # Stage 3: BM25 keyword search via FTS5
    if bm25_enabled:
        strategies_used.append("bm25")
        fts_map = {
            "short": ("stm_fts", "short_term_memory", "short_term"),
            "mid": ("mtm_fts", "midterm_memory", "midterm"),
            "long": ("ltm_fts", "long_term_memory", "long_term"),
        }
        for tier_key, (fts_table, base_table, label) in fts_map.items():
            if tier_key not in tiers_to_search:
                continue
            bm25_hits = _bm25_search(conn, fts_table, base_table, label, query, agent_id, top_k)
            for mid, bm25_score, entry in bm25_hits:
                if mid in all_results:
                    all_results[mid]["bm25"] = bm25_score
                else:
                    all_results[mid] = {"entry": entry, "semantic": 0.0, "bm25": bm25_score, "graph": 0.0, "temporal": 0.0}

    # Stage 4: Graph traversal
    if graph_enabled:
        strategies_used.append("graph")
        query_entities = _identify_entities(conn, query_embedding, top_k=3)
        for ent in query_entities:
            relations = crud.list_relations_for_node(conn, ent["id"], "entities")
            for rel in relations:
                other_id = rel["target_id"] if rel["source_id"] == ent["id"] else rel["source_id"]
                other_table = rel["target_table"] if rel["source_id"] == ent["id"] else rel["source_table"]
                if other_table in ("short_term_memory", "midterm_memory", "long_term_memory"):
                    if other_id not in all_results:
                        row = conn.execute(f"SELECT * FROM {other_table} WHERE id = ?", (other_id,)).fetchone()
                        if row:
                            entry = dict(row)
                            tier_label = {"short_term_memory": "short_term", "midterm_memory": "midterm", "long_term_memory": "long_term"}.get(other_table, other_table)
                            entry["tier"] = tier_label
                            entry.pop("embedding", None)
                            all_results[other_id] = {"entry": entry, "semantic": 0.0, "bm25": 0.0, "graph": rel.get("weight", 0.5), "temporal": 0.0}
                    else:
                        all_results[other_id]["graph"] = max(all_results[other_id]["graph"], rel.get("weight", 0.5))

    # Stage 5: Temporal weighting
    if temporal_enabled:
        strategies_used.append("temporal")
        now = datetime.utcnow()
        for mid, data in all_results.items():
            entry = data["entry"]
            ts_str = entry.get("timestamp") or entry.get("created_at") or entry.get("last_accessed")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str)
                    days_old = max((now - ts).total_seconds() / 86400, 0)
                    data["temporal"] = temporal_curve ** days_old
                except (ValueError, TypeError):
                    data["temporal"] = 0.5
            else:
                data["temporal"] = 0.5

    # Stage 6: Merge scores and rank
    for mid, data in all_results.items():
        combined = (
            data["semantic"] * 0.4 +
            data["bm25"] * 0.25 +
            data["graph"] * 0.2 +
            data["temporal"] * 0.15
        )
        data["combined_score"] = round(combined, 4)
        data["entry"]["similarity_score"] = round(data["semantic"], 4)
        data["entry"]["combined_score"] = data["combined_score"]
        data["entry"]["retrieval_strategies"] = {
            k: round(data[k], 4) for k in ("semantic", "bm25", "graph", "temporal") if data[k] > 0
        }

    # Sort by combined score, split back into tiers
    ranked = sorted(all_results.values(), key=lambda x: x["combined_score"], reverse=True)
    memories = {"short_term": [], "midterm": [], "long_term": []}
    for data in ranked:
        tier = data["entry"].get("tier", "")
        if tier in memories and len(memories[tier]) < top_k:
            memories[tier].append(data["entry"])

    # Stage 7: Entity identification and expansion
    entities = _identify_entities(conn, query_embedding, top_k=5)

    # Stage 8: Goal matching
    goals = _match_goals(conn, query_embedding, threshold=goal_threshold)

    # Stage 9: Skill matching
    skills = _match_skills(conn, query_embedding, threshold=skill_threshold)

    return {
        "memories": memories,
        "entities": entities,
        "goals": goals,
        "skills": skills,
        "retrieval_strategies": strategies_used,
    }


def _load_retrieval_config(conn):
    """Load retrieval-related config values from meta_config."""
    keys = [
        "context_results_per_tier",
        "goal_similarity_threshold",
        "skill_similarity_threshold",
        "bm25_enabled",
        "graph_traversal_enabled",
        "temporal_boost_enabled",
        "temporal_decay_curve",
    ]
    config = {}
    for key in keys:
        val = crud.get_config_value(conn, key)
        if val is not None:
            config[key] = val
    return config


def _get_memory_candidates(conn, table, filters, agent_id=None):
    """Fetch (id, embedding) pairs from a memory table with optional filters and agent scoping."""
    query = f"SELECT id, embedding FROM {table} WHERE embedding IS NOT NULL"
    params = []

    if agent_id:
        query += " AND (agent_id = ? OR agent_id = 'shared')"
        params.append(agent_id)

    confidence_min = filters.get("confidence_min")
    if confidence_min is not None and table in ("midterm_memory", "long_term_memory"):
        query += " AND confidence >= ?"
        params.append(confidence_min)

    time_range = filters.get("time_range")
    if time_range:
        ts_col = "timestamp" if table == "short_term_memory" else "created_at"
        if time_range.get("start"):
            query += f" AND {ts_col} >= ?"
            params.append(time_range["start"])
        if time_range.get("end"):
            query += f" AND {ts_col} <= ?"
            params.append(time_range["end"])

    rows = conn.execute(query, params).fetchall()
    return [(r["id"], r["embedding"]) for r in rows]


def _bm25_search(conn, fts_table, base_table, tier_label, query_text, agent_id, top_k):
    """Run BM25 keyword search via FTS5. Returns list of (id, score, entry) tuples."""
    results = []
    try:
        safe_query = query_text.replace('"', '').replace("'", '')
        tokens = safe_query.split()
        if not tokens:
            return []
        fts_query = ' OR '.join(tokens)

        sql = f"""
            SELECT b.id, b.*, rank
            FROM {fts_table} f
            JOIN {base_table} b ON b.rowid = f.rowid
            WHERE {fts_table} MATCH ?
        """
        params = [fts_query]

        if agent_id:
            sql += " AND (b.agent_id = ? OR b.agent_id = 'shared')"
            params.append(agent_id)

        sql += f" ORDER BY rank LIMIT {top_k}"

        rows = conn.execute(sql, params).fetchall()
        for row in rows:
            entry = dict(row)
            rank = abs(entry.pop("rank", 0))
            score = 1.0 / (1.0 + rank) if rank else 0.5
            entry["tier"] = tier_label
            entry.pop("embedding", None)
            results.append((entry["id"], score, entry))
    except Exception:
        pass
    return results


def _identify_entities(conn, query_embedding, top_k=5):
    """Find entities semantically related to the query and expand their context."""
    rows = conn.execute(
        "SELECT id, embedding FROM entities WHERE embedding IS NOT NULL"
    ).fetchall()
    candidates = [(r["id"], r["embedding"]) for r in rows]
    if not candidates:
        return []

    results = semantic_search(query_embedding, candidates, top_k=top_k)
    entities = []
    for eid, score in results:
        if score < 0.3:
            continue
        entity = crud.get_entity(conn, eid)
        if entity:
            entity["similarity_score"] = round(score, 4)
            entity.pop("embedding", None)
            # Get related memories
            relations = crud.list_relations_for_node(conn, eid, "entities")
            entity["relations"] = [
                {k: v for k, v in dict(r).items() if k != "embedding"}
                for r in relations
            ]
            entities.append(entity)
    return entities


def _match_goals(conn, query_embedding, threshold=0.7):
    """Match query against active goal embeddings."""
    rows = conn.execute(
        "SELECT id, embedding FROM goals WHERE status = 'active' AND embedding IS NOT NULL"
    ).fetchall()
    candidates = [(r["id"], r["embedding"]) for r in rows]
    if not candidates:
        return []

    results = semantic_search(query_embedding, candidates, top_k=5)
    goals = []
    for gid, score in results:
        if score < threshold:
            continue
        goal = crud.get_goal(conn, gid)
        if goal:
            goal["similarity_score"] = round(score, 4)
            goal.pop("embedding", None)
            goals.append(goal)
    return goals


def _match_skills(conn, query_embedding, threshold=0.6):
    """Match query against skill description embeddings."""
    rows = conn.execute(
        "SELECT id, embedding FROM skills WHERE embedding IS NOT NULL"
    ).fetchall()
    candidates = [(r["id"], r["embedding"]) for r in rows]
    if not candidates:
        return []

    results = semantic_search(query_embedding, candidates, top_k=5)
    skills = []
    for sid, score in results:
        if score < threshold:
            continue
        skill = crud.get_skill(conn, sid)
        if skill:
            skill["similarity_score"] = round(score, 4)
            skill.pop("embedding", None)
            # Get active implementation info
            impls = crud.list_skill_implementations(conn, sid, active_only=True)
            if impls:
                impl = impls[0]
                skill["active_implementation"] = {
                    "language": impl["language"],
                    "dependencies": impl["dependencies"],
                    "version": impl["version"],
                }
            skills.append(skill)
    return skills
