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


def retrieve_context(conn, query, filters=None, config=None):
    """
    Execute the full multi-stage context retrieval pipeline.

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

    Returns:
        dict with keys: memories, entities, goals, skills, query_embedding_generated
    """
    if filters is None:
        filters = {}
    if config is None:
        config = _load_retrieval_config(conn)

    top_k = int(config.get("context_results_per_tier", 10))
    goal_threshold = float(config.get("goal_similarity_threshold", 0.7))
    skill_threshold = float(config.get("skill_similarity_threshold", 0.6))

    # Stage 1: Generate query embedding
    query_embedding = generate_embedding(query)
    query_blob = embedding_to_blob(query_embedding)

    # Stage 2: Multi-tier memory search
    tiers_to_search = filters.get("tier", ["short", "mid", "long"])
    memories = {}

    tier_map = {
        "short": ("short_term_memory", "short_term"),
        "mid": ("midterm_memory", "midterm"),
        "long": ("long_term_memory", "long_term"),
    }

    for tier_key, (table, label) in tier_map.items():
        if tier_key not in tiers_to_search:
            continue
        candidates = _get_memory_candidates(conn, table, filters)
        results = semantic_search(query_embedding, candidates, top_k=top_k)
        tier_memories = []
        for mid, score in results:
            row = conn.execute(
                f"SELECT * FROM {table} WHERE id = ?", (mid,)
            ).fetchone()
            if row:
                entry = dict(row)
                entry["similarity_score"] = round(score, 4)
                entry["tier"] = label
                entry.pop("embedding", None)
                tier_memories.append(entry)
        memories[label] = tier_memories

    # Stage 3: Entity identification and expansion
    entities = _identify_entities(conn, query_embedding, top_k=5)

    # Stage 4: Goal matching
    goals = _match_goals(conn, query_embedding, threshold=goal_threshold)

    # Stage 5: Skill matching
    skills = _match_skills(conn, query_embedding, threshold=skill_threshold)

    return {
        "memories": memories,
        "entities": entities,
        "goals": goals,
        "skills": skills,
        "query_embedding_generated": True,
    }


def _load_retrieval_config(conn):
    """Load retrieval-related config values from meta_config."""
    keys = [
        "context_results_per_tier",
        "goal_similarity_threshold",
        "skill_similarity_threshold",
    ]
    config = {}
    for key in keys:
        val = crud.get_config_value(conn, key)
        if val is not None:
            config[key] = val
    return config


def _get_memory_candidates(conn, table, filters):
    """Fetch (id, embedding) pairs from a memory table with optional filters."""
    query = f"SELECT id, embedding FROM {table} WHERE embedding IS NOT NULL"
    params = []

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
