"""
Context retrieval pipeline for AgentDB v1.5/v1.6.

Implements the multi-stage retrieval pipeline:
1. Query normalization + embedding generation
2. Semantic vector search across all three memory tiers
3. BM25 keyword search via FTS5
4. Graph traversal (entity → relations → memories)
5. Temporal weighting (exponential recency decay)
6. Score fusion (0.4 × semantic + 0.25 × BM25 + 0.2 × graph + 0.15 × temporal)
7. Cross-encoder reranking (top-N candidates reranked against query)
8. Pinned memory injection (always-in-context memories at top of payload)
9. Context assembly with token budget enforcement

Returns a unified context payload with labeled sections.
"""

import json
import uuid
from datetime import datetime

from agentdb import crud
from agentdb.embeddings import (
    generate_embedding,
    embedding_to_blob,
    blob_to_embedding,
    cosine_similarity,
    semantic_search,
)


# ── Cross-encoder reranker (lazy-loaded) ──

_reranker_model = None


def _get_reranker(model_name="cross-encoder/ms-marco-MiniLM-L-6-v2"):
    """Lazy-load the cross-encoder reranker model."""
    global _reranker_model
    if _reranker_model is None:
        try:
            from sentence_transformers import CrossEncoder
            _reranker_model = CrossEncoder(model_name)
        except Exception:
            _reranker_model = False  # Mark as unavailable
    return _reranker_model if _reranker_model is not False else None


def rerank_candidates(query, candidates, model_name=None):
    """
    Rerank a list of (id, content, data) tuples using the cross-encoder.

    Returns the same tuples reordered by cross-encoder relevance score.
    Each tuple's data dict gets a 'reranker_score' key added.
    """
    if not candidates:
        return candidates
    reranker = _get_reranker(model_name) if model_name else _get_reranker()
    if reranker is None:
        return candidates

    pairs = [(query, c[1]) for c in candidates]
    scores = reranker.predict(pairs)

    for i, score in enumerate(scores):
        candidates[i][2]["reranker_score"] = float(score)

    # Sort by reranker score descending
    return sorted(candidates, key=lambda x: x[2].get("reranker_score", 0), reverse=True)


def retrieve_context(conn, query, filters=None, config=None, agent_id=None,
                     include_agents=None):
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
        include_agents: list[str] of additional agent IDs whose memories are
            included alongside agent_id and 'shared'.  Useful for multi-agent
            workspaces where agents need selective visibility into each other's
            knowledge (e.g. a supervisor reading a sub-agent's memories).

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
    # Compute once; used in semantic, BM25, and graph stages for consistent scoping
    _agent_set = _build_agent_set(agent_id, include_agents)

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
        candidates = _get_memory_candidates(conn, table, filters,
                                            agent_id=agent_id,
                                            include_agents=include_agents)
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
            bm25_hits = _bm25_search(conn, fts_table, base_table, label, query,
                                     agent_id, top_k, include_agents=include_agents)
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
                            # Respect agent scope: skip cross-agent memories unless included
                            if _agent_set is not None and entry.get("agent_id") not in _agent_set:
                                continue
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

    # Stage 7: Cross-encoder reranking
    reranker_enabled = config.get("reranker_enabled", "false") == "true"
    skip_rerank = (filters or {}).get("skip_rerank", False)
    reranker_candidates_count = int(config.get("reranker_candidates", 20))

    ranked = sorted(all_results.values(), key=lambda x: x["combined_score"], reverse=True)

    if reranker_enabled and not skip_rerank and ranked:
        strategies_used.append("reranker")
        # Prepare top-N candidates for reranking
        to_rerank = ranked[:reranker_candidates_count]
        rerank_input = [
            [mid_data["entry"].get("id", ""), mid_data["entry"].get("content", ""), mid_data]
            for mid_data in to_rerank
        ]
        reranked = rerank_candidates(query, rerank_input,
                                     model_name=config.get("reranker_model"))
        # Merge reranked portion back; keep the rest in original order
        reranked_data = [item[2] for item in reranked]
        remaining = ranked[reranker_candidates_count:]
        ranked = reranked_data + remaining

    # Split into tiers
    memories = {"short_term": [], "midterm": [], "long_term": []}
    for data in ranked:
        tier = data["entry"].get("tier", "")
        if tier in memories and len(memories[tier]) < top_k:
            memories[tier].append(data["entry"])

    # Stage 8: Pinned memory injection
    pinned = []
    pinned_ids = []
    try:
        pinned_contents = crud.get_pinned_memory_contents(conn, agent_id)
        for pc in pinned_contents:
            pinned.append(pc)
            pinned_ids.append(pc.get("pin_id") or pc.get("id"))
    except Exception:
        pass  # pinned_memories table may not exist on older databases

    # Stage 9: Entity identification and expansion
    entities = _identify_entities(conn, query_embedding, top_k=5)

    # Stage 10: Goal matching
    goals = _match_goals(conn, query_embedding, threshold=goal_threshold)

    # Stage 11: Skill matching
    skills = _match_skills(conn, query_embedding, threshold=skill_threshold)

    # Stage 12: Context snapshot auto-capture
    snapshot_id = None
    try:
        memory_ids_for_snapshot = []
        for tier, mems in memories.items():
            for m in mems:
                strategy_info = m.get("retrieval_strategies", {})
                memory_ids_for_snapshot.append({
                    "id": m.get("id"),
                    "table": {"short_term": "short_term_memory",
                              "midterm": "midterm_memory",
                              "long_term": "long_term_memory"}.get(tier, tier),
                    "strategies": strategy_info,
                })
        skill_ids = [s.get("id") for s in skills]
        relation_ids = []
        for ent in entities:
            for rel in ent.get("relations", []):
                if rel.get("id"):
                    relation_ids.append(rel["id"])
        goal_id = goals[0].get("id") if goals else None

        snapshot_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO context_snapshots
               (id, timestamp, trigger_description, memory_ids, skill_ids,
                relation_ids, goal_id, pinned_memory_ids, session_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (snapshot_id, datetime.utcnow().isoformat(),
             f"retrieve_context: {query[:100]}",
             json.dumps(memory_ids_for_snapshot),
             json.dumps(skill_ids),
             json.dumps(relation_ids),
             goal_id,
             json.dumps(pinned_ids) if pinned_ids else None,
             None),  # session_id filled by middleware if available
        )
        conn.commit()
    except Exception:
        snapshot_id = None  # Non-critical; don't break retrieval

    return {
        "memories": memories,
        "pinned": pinned,
        "entities": entities,
        "goals": goals,
        "skills": skills,
        "retrieval_strategies": strategies_used,
        "snapshot_id": snapshot_id,
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
        "reranker_enabled",
        "reranker_model",
        "reranker_candidates",
    ]
    config = {}
    for key in keys:
        val = crud.get_config_value(conn, key)
        if val is not None:
            config[key] = val
    return config


def _build_agent_set(agent_id, include_agents):
    """
    Build the set of agent IDs to include in a scoped query.

    Rules:
    - No agent_id and no include_agents → None (unscoped, return all)
    - agent_id set → always includes agent_id + 'shared'
    - include_agents → each listed agent ID is also included

    Returns a list suitable for SQL IN (?) or None for no filter.
    """
    if not agent_id and not include_agents:
        return None
    ids = {"shared"}
    if agent_id:
        ids.add(agent_id)
    if include_agents:
        ids.update(include_agents)
    return list(ids)


def _get_memory_candidates(conn, table, filters, agent_id=None, include_agents=None):
    """Fetch (id, embedding) pairs from a memory table with optional filters and agent scoping.

    agent_id scopes to that agent + 'shared'.  include_agents extends that set
    to additional named agents (useful for cross-agent reads without opening
    full unscoped access).
    """
    query = f"SELECT id, embedding FROM {table} WHERE embedding IS NOT NULL"
    params = []

    agent_set = _build_agent_set(agent_id, include_agents)
    if agent_set is not None:
        placeholders = ",".join("?" * len(agent_set))
        query += f" AND agent_id IN ({placeholders})"
        params.extend(agent_set)

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


def _bm25_search(conn, fts_table, base_table, tier_label, query_text, agent_id,
                 top_k, include_agents=None):
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

        agent_set = _build_agent_set(agent_id, include_agents)
        if agent_set is not None:
            placeholders = ",".join("?" * len(agent_set))
            sql += f" AND b.agent_id IN ({placeholders})"
            params.extend(agent_set)

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
