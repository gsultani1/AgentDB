"""
Sleep-time reflection engine for AgentDB.

Implements PRD Section 9 idle-time processing:

1. Full consolidation cycle (STM→MTM→LTM, decay, feedback)
2. Goal monitoring — scan recent memories for goal-relevant signals and
   emit goal_match notifications when similarity exceeds threshold
3. Graph pruning — remove stale / low-weight relations that would otherwise
   accumulate forever and slow retrieval
4. Cycle summary notification — consolidation_complete entry so the
   operator dashboard can see the last sleep-time run at a glance
"""

import json
from datetime import datetime, timedelta

from agentdb import crud
from agentdb.consolidation import run_consolidation_cycle
from agentdb.embeddings import semantic_search


def run_sleep_cycle(conn, config=None):
    """
    Execute a full sleep-time reflection cycle.

    Args:
        conn: sqlite3.Connection
        config: optional dict of meta_config overrides (loads from DB if None)

    Returns:
        dict with summary of all actions taken.
    """
    if config is None:
        config = _load_sleep_config(conn)

    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "consolidation": {},
        "goals_checked": 0,
        "goal_notifications": 0,
        "relations_pruned": 0,
        "notifications_created": 0,
    }

    if config.get("sleep_reflection_enabled", "true") != "true":
        results["message"] = "Sleep reflection disabled via config"
        return results

    # Phase 1: Full consolidation (STM→MTM→LTM + decay + feedback)
    consolidation_result = run_consolidation_cycle(conn)
    results["consolidation"] = consolidation_result

    # Phase 2: Goal monitoring
    goal_results = _monitor_goals(conn, config)
    results["goals_checked"] = goal_results["checked"]
    results["goal_notifications"] = goal_results["notifications"]

    # Phase 3: Graph pruning
    prune_results = _prune_graph(conn, config)
    results["relations_pruned"] = prune_results["pruned"]

    # Phase 4: Summary notification
    notif_count = _create_cycle_notification(conn, results, consolidation_result)
    results["notifications_created"] = notif_count

    crud.set_config(conn, "last_sleep_cycle_timestamp", results["timestamp"])
    return results


# ──────────────────────────────────────────────────────────────────────────────
# Phase 2 — Goal monitoring
# ──────────────────────────────────────────────────────────────────────────────

def _monitor_goals(conn, config):
    """
    For each active goal, search recent STM for related observations.
    When similarity exceeds threshold, emit a goal_match notification so
    the operator knows the agent is on track without a full context pull.
    """
    threshold = float(config.get("goal_similarity_threshold", "0.7"))
    window_hours = int(config.get("sleep_goal_monitor_window_hours", "24"))
    cutoff = (datetime.utcnow() - timedelta(hours=window_hours)).isoformat()

    active_goals = conn.execute(
        "SELECT id, description, embedding FROM goals "
        "WHERE status = 'active' AND embedding IS NOT NULL"
    ).fetchall()

    recent_stm = conn.execute(
        "SELECT id, embedding FROM short_term_memory "
        "WHERE timestamp > ? AND embedding IS NOT NULL AND status = 'active'",
        (cutoff,),
    ).fetchall()
    candidates = [(r["id"], r["embedding"]) for r in recent_stm]

    checked = 0
    notifications = 0

    for goal in active_goals:
        checked += 1
        if not candidates:
            continue

        matches = semantic_search(goal["embedding"], candidates, top_k=5)
        strong = [(mid, score) for mid, score in matches if score >= threshold]
        if not strong:
            continue

        top_score = strong[0][1]
        memory_ids = [mid for mid, _ in strong]
        crud.create_notification(
            conn,
            title=f"Goal progress: {goal['description'][:80]}",
            trigger_type="goal_match",
            agent_id="default",
            body=(
                f"{len(strong)} recent observation(s) relate to this goal "
                f"(top similarity: {top_score:.2f})."
            ),
            priority="medium",
            related_ids=json.dumps({"goal_id": goal["id"], "memory_ids": memory_ids}),
        )
        notifications += 1

    return {"checked": checked, "notifications": notifications}


# ──────────────────────────────────────────────────────────────────────────────
# Phase 3 — Graph pruning
# ──────────────────────────────────────────────────────────────────────────────

def _prune_graph(conn, config):
    """
    Remove relations whose weight has fallen below the configured minimum.
    Relations created by the user (context = 'user_authored') are exempt.
    Also remove relations older than `sleep_graph_pruning_threshold_days`
    where both endpoints no longer exist (orphan cleanup complement).
    """
    min_weight = float(config.get("min_relation_weight", "0.05"))
    pruning_days = int(config.get("sleep_graph_pruning_threshold_days", "60"))
    age_cutoff = (datetime.utcnow() - timedelta(days=pruning_days)).isoformat()

    # Low-weight relations (skip user-authored)
    low_weight_rows = conn.execute(
        "SELECT id FROM relations WHERE weight < ? "
        "AND (context IS NULL OR context != 'user_authored')",
        (min_weight,),
    ).fetchall()

    # Ancient relations pointing into tables that no longer have the row
    stale_rows = conn.execute(
        "SELECT id FROM relations WHERE created_at < ?",
        (age_cutoff,),
    ).fetchall()

    # De-duplicate
    to_delete = {r["id"] for r in low_weight_rows} | {r["id"] for r in stale_rows}

    # Verify stale relations actually have a missing endpoint before deleting
    checked_to_delete = set()
    for rid in to_delete:
        row = conn.execute("SELECT * FROM relations WHERE id = ?", (rid,)).fetchone()
        if not row:
            continue
        # Always delete low-weight; only delete stale if an endpoint is gone
        if rid in {r["id"] for r in low_weight_rows}:
            checked_to_delete.add(rid)
        else:
            src_exists = conn.execute(
                f"SELECT 1 FROM {row['source_table']} WHERE id = ?",
                (row["source_id"],),
            ).fetchone()
            tgt_exists = conn.execute(
                f"SELECT 1 FROM {row['target_table']} WHERE id = ?",
                (row["target_id"],),
            ).fetchone()
            if not src_exists or not tgt_exists:
                checked_to_delete.add(rid)

    for rid in checked_to_delete:
        conn.execute("DELETE FROM relations WHERE id = ?", (rid,))
    conn.commit()

    return {"pruned": len(checked_to_delete)}


# ──────────────────────────────────────────────────────────────────────────────
# Phase 4 — Summary notification
# ──────────────────────────────────────────────────────────────────────────────

def _create_cycle_notification(conn, results, consolidation_result):
    """Create a single consolidation_complete notification with cycle stats."""
    body = (
        f"STM→MTM: {consolidation_result.get('short_to_mid_promoted', 0)}, "
        f"MTM→LTM: {consolidation_result.get('mid_to_long_promoted', 0)}, "
        f"Contradictions: {consolidation_result.get('contradictions_found', 0)}, "
        f"Decayed: {consolidation_result.get('entries_decayed', 0)}, "
        f"Pruned: {consolidation_result.get('entries_pruned', 0)}, "
        f"Relations pruned: {results.get('relations_pruned', 0)}, "
        f"Goal notifications: {results.get('goal_notifications', 0)}"
    )
    total = sum([
        consolidation_result.get("short_to_mid_promoted", 0),
        consolidation_result.get("mid_to_long_promoted", 0),
        results.get("goal_notifications", 0),
        results.get("relations_pruned", 0),
    ])
    priority = "low" if total == 0 else "medium"
    crud.create_notification(
        conn,
        title="Sleep-time reflection complete",
        trigger_type="consolidation_complete",
        agent_id="default",
        body=body,
        priority=priority,
        related_ids=json.dumps({"cycle_summary": results}),
    )
    return 1


# ──────────────────────────────────────────────────────────────────────────────
# Config helpers
# ──────────────────────────────────────────────────────────────────────────────

def _load_sleep_config(conn):
    keys = [
        "sleep_reflection_enabled",
        "sleep_goal_monitor_window_hours",
        "sleep_graph_pruning_threshold_days",
        "min_relation_weight",
        "goal_similarity_threshold",
    ]
    config = {}
    for key in keys:
        val = crud.get_config_value(conn, key)
        if val is not None:
            config[key] = val
    return config
