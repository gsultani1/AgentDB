"""
Sleep-time reflection engine for AgentDB v1.5/v1.6.

Implements idle-time processing:

1. Full consolidation cycle (STM→MTM→LTM, decay, feedback)
2. Goal monitoring — scan recent memories for goal-relevant signals and
   emit goal_match notifications when similarity exceeds threshold
3. Graph pruning — remove stale / low-weight relations that would otherwise
   accumulate forever and slow retrieval
4. Custom alert condition evaluation — operator-defined rules
5. Cycle summary notification — consolidation_complete entry so the
   operator dashboard can see the last sleep-time run at a glance

Also provides idle detection for automatic sleep-time activation.
"""

import json
import os
import threading
import time as _time
from datetime import datetime, timedelta

from agentdb import crud
from agentdb.consolidation import run_consolidation_cycle
from agentdb.embeddings import semantic_search


# ── Idle Detection ──────────────────────────────────────────────────────

_last_agent_api_call = _time.time()
_is_idle = False
_idle_detector_thread = None
_idle_detector_running = False


def record_agent_api_call():
    """Called on every /api/agent/* request to reset idle timer."""
    global _last_agent_api_call, _is_idle
    _last_agent_api_call = _time.time()
    _is_idle = False


def is_idle():
    """Return True if the system is currently in idle state."""
    return _is_idle


def idle_since():
    """Return the timestamp when idle state began, or None if active."""
    if not _is_idle:
        return None
    return datetime.utcfromtimestamp(_last_agent_api_call).isoformat()


def start_idle_detector(conn_factory, threshold_seconds=300, check_interval=10):
    """
    Start a background thread that monitors idle state and triggers
    sleep-time processing when the idle threshold is exceeded.

    Args:
        conn_factory: callable that returns a sqlite3.Connection
        threshold_seconds: seconds of inactivity before triggering sleep
        check_interval: seconds between idle checks
    """
    global _idle_detector_thread, _idle_detector_running

    if _idle_detector_running:
        return

    _idle_detector_running = True

    def _detector_loop():
        global _is_idle
        while _idle_detector_running:
            elapsed = _time.time() - _last_agent_api_call
            was_idle = _is_idle

            if elapsed >= threshold_seconds:
                _is_idle = True
                if not was_idle:
                    # Just became idle — run a sleep cycle
                    try:
                        conn = conn_factory()
                        run_sleep_cycle(conn)
                        conn.close()
                    except Exception:
                        pass
            else:
                _is_idle = False

            _time.sleep(check_interval)

    _idle_detector_thread = threading.Thread(target=_detector_loop, daemon=True,
                                             name="agentdb-idle-detector")
    _idle_detector_thread.start()


def stop_idle_detector():
    """Stop the idle detection background thread."""
    global _idle_detector_running
    _idle_detector_running = False


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

    # Phase 4: Custom alert condition evaluation
    alert_results = _evaluate_alert_conditions(conn, config)
    results["alerts_fired"] = alert_results["fired"]
    results["alerts_checked"] = alert_results["checked"]

    # Phase 5: Summary notification
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
    where an endpoint no longer exists (orphan cleanup).

    Optimized per PRD 16.4: uses single queries for low-weight identification
    and JOIN-based existence checks per content table instead of per-relation
    sequential queries.
    """
    from agentdb.schema import CONTENT_TABLES

    min_weight = float(config.get("min_relation_weight", "0.05"))
    pruning_days = int(config.get("sleep_graph_pruning_threshold_days", "60"))
    age_cutoff = (datetime.utcnow() - timedelta(days=pruning_days)).isoformat()

    to_delete = set()

    # 1. Low-weight relations — single query, always delete (skip user-authored)
    low_weight_rows = conn.execute(
        "SELECT id FROM relations WHERE weight < ? "
        "AND (context IS NULL OR context != 'user_authored')",
        (min_weight,),
    ).fetchall()
    to_delete.update(r["id"] for r in low_weight_rows)

    # 2. Stale orphan detection — JOIN-based per content table
    #    Find stale relations where source or target endpoint is missing,
    #    using one LEFT JOIN per content table instead of per-relation queries.
    for content_table in CONTENT_TABLES:
        # Stale relations with missing SOURCE in this content table
        orphan_src = conn.execute(
            f"""SELECT r.id FROM relations r
                LEFT JOIN {content_table} ct ON ct.id = r.source_id
                WHERE r.source_table = ?
                  AND r.created_at < ?
                  AND ct.id IS NULL""",
            (content_table, age_cutoff),
        ).fetchall()
        to_delete.update(r["id"] for r in orphan_src)

        # Stale relations with missing TARGET in this content table
        orphan_tgt = conn.execute(
            f"""SELECT r.id FROM relations r
                LEFT JOIN {content_table} ct ON ct.id = r.target_id
                WHERE r.target_table = ?
                  AND r.created_at < ?
                  AND ct.id IS NULL""",
            (content_table, age_cutoff),
        ).fetchall()
        to_delete.update(r["id"] for r in orphan_tgt)

    # Batch delete
    if to_delete:
        # SQLite supports up to 999 params; batch if needed
        id_list = list(to_delete)
        batch_size = 500
        for i in range(0, len(id_list), batch_size):
            batch = id_list[i:i + batch_size]
            placeholders = ",".join("?" * len(batch))
            conn.execute(f"DELETE FROM relations WHERE id IN ({placeholders})", batch)
        conn.commit()

    return {"pruned": len(to_delete)}


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
# Phase 4 — Custom alert conditions
# ──────────────────────────────────────────────────────────────────────────────

def _evaluate_alert_conditions(conn, config):
    """
    Evaluate operator-defined custom alert rules stored in meta_config.

    Supported condition types:
    - entity_mention: Alert when a specific entity is mentioned in recent STM
    - contradiction_detected: Alert when contradictions exist in a tier
    - db_size_threshold: Alert when database exceeds a size threshold
    - content_keyword: Alert when keywords appear in recent memories
    - goal_match: Alert when goal similarity exceeds a custom threshold
    - memory_count_threshold: Alert when a tier exceeds N entries
    """
    rules_json = crud.get_config_value(conn, "custom_alert_rules")
    if not rules_json:
        return {"checked": 0, "fired": 0}

    try:
        rules = json.loads(rules_json)
    except (json.JSONDecodeError, TypeError):
        return {"checked": 0, "fired": 0}

    if not isinstance(rules, list):
        return {"checked": 0, "fired": 0}

    now = datetime.utcnow()
    checked = 0
    fired = 0

    for rule in rules:
        if not rule.get("enabled", True):
            continue
        checked += 1

        # Check cooldown
        last_fired = rule.get("last_fired_at")
        cooldown = rule.get("cooldown_minutes", 60)
        if last_fired:
            try:
                last_dt = datetime.fromisoformat(last_fired)
                if (now - last_dt).total_seconds() < cooldown * 60:
                    continue
            except (ValueError, TypeError):
                pass

        condition_type = rule.get("condition_type", "")
        params = rule.get("parameters", {})
        triggered = False

        try:
            if condition_type == "entity_mention":
                triggered = _check_entity_mention(conn, params)
            elif condition_type == "contradiction_detected":
                triggered = _check_contradiction(conn, params)
            elif condition_type == "db_size_threshold":
                triggered = _check_db_size(conn, params)
            elif condition_type == "content_keyword":
                triggered = _check_content_keyword(conn, params)
            elif condition_type == "goal_match":
                triggered = _check_goal_match(conn, params)
            elif condition_type == "memory_count_threshold":
                triggered = _check_memory_count(conn, params)
        except Exception:
            continue

        if triggered:
            fired += 1
            rule["last_fired_at"] = now.isoformat()
            crud.create_notification(
                conn,
                title=f"Alert: {rule.get('name', condition_type)}",
                trigger_type="alert_condition",
                agent_id="default",
                body=f"Custom alert condition '{rule.get('name', '')}' fired. Type: {condition_type}",
                priority=rule.get("priority", "medium"),
                related_ids=json.dumps({"rule_id": rule.get("id"), "condition_type": condition_type}),
            )

    # Save updated rules with last_fired_at timestamps
    crud.set_config(conn, "custom_alert_rules", json.dumps(rules))
    return {"checked": checked, "fired": fired}


def _check_entity_mention(conn, params):
    """Check if an entity was mentioned in recent STM."""
    entity_name = params.get("entity_name", "")
    if not entity_name:
        return False
    cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    row = conn.execute(
        "SELECT COUNT(*) FROM short_term_memory WHERE timestamp > ? AND content LIKE ?",
        (cutoff, f"%{entity_name}%"),
    ).fetchone()
    return row[0] > 0 if row else False


def _check_contradiction(conn, params):
    """Check for unresolved contradictions."""
    table = params.get("table", "")
    min_conf = float(params.get("min_confidence", 0))
    query = "SELECT COUNT(*) FROM contradictions WHERE resolution = 'unresolved'"
    p = []
    if table:
        query += " AND (memory_a_table = ? OR memory_b_table = ?)"
        p.extend([table, table])
    row = conn.execute(query, p).fetchone()
    return row[0] > 0 if row else False


def _check_db_size(conn, params):
    """Check if database file exceeds size threshold."""
    max_mb = float(params.get("max_mb", 500))
    try:
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        page_count = conn.execute("PRAGMA page_count").fetchone()[0]
        size_mb = (page_size * page_count) / (1024 * 1024)
        return size_mb > max_mb
    except Exception:
        return False


def _check_content_keyword(conn, params):
    """Check if keywords appear in recent memories."""
    keywords = params.get("keywords", [])
    tier = params.get("tier", "short_term_memory")
    if not keywords:
        return False
    cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    ts_col = "timestamp" if tier == "short_term_memory" else "created_at"
    for kw in keywords:
        row = conn.execute(
            f"SELECT COUNT(*) FROM {tier} WHERE {ts_col} > ? AND content LIKE ?",
            (cutoff, f"%{kw}%"),
        ).fetchone()
        if row and row[0] > 0:
            return True
    return False


def _check_goal_match(conn, params):
    """Check if any goal has recent high-similarity matches."""
    threshold = float(params.get("threshold", 0.8))
    # Reuse the goal monitoring logic
    cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    goals = conn.execute(
        "SELECT id, embedding FROM goals WHERE status = 'active' AND embedding IS NOT NULL"
    ).fetchall()
    candidates = [(r["id"], r["embedding"]) for r in conn.execute(
        "SELECT id, embedding FROM short_term_memory WHERE timestamp > ? AND embedding IS NOT NULL",
        (cutoff,),
    ).fetchall()]
    if not candidates or not goals:
        return False
    for goal in goals:
        matches = semantic_search(goal["embedding"], candidates, top_k=1)
        if matches and matches[0][1] >= threshold:
            return True
    return False


def _check_memory_count(conn, params):
    """Check if a memory tier exceeds a count threshold."""
    tier_map = {"short": "short_term_memory", "mid": "midterm_memory", "long": "long_term_memory"}
    tier = tier_map.get(params.get("tier", "short"), "short_term_memory")
    max_count = int(params.get("max_count", 10000))
    row = conn.execute(f"SELECT COUNT(*) FROM {tier}").fetchone()
    return row[0] > max_count if row else False


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
        "custom_alert_rules",
    ]
    config = {}
    for key in keys:
        val = crud.get_config_value(conn, key)
        if val is not None:
            config[key] = val
    return config
