"""
Consolidation Engine for AgentDB.

Implements PRD Section 8:
- Short-to-midterm consolidation with configurable clustering threshold
- Midterm-to-long-term promotion with contradiction detection
- Decay and pruning (user-authored entries exempt)
- Feedback processing loop
- Scheduled execution via configurable interval
"""

import json
import threading
import time
from datetime import datetime, timedelta

from agentdb import crud
from agentdb.embeddings import (
    generate_embedding,
    embedding_to_blob,
    blob_to_embedding,
    semantic_search,
)


def run_consolidation_cycle(conn, config=None):
    """
    Execute a full consolidation cycle.

    Args:
        conn: sqlite3.Connection
        config: dict of meta_config overrides (loads from DB if None)

    Returns:
        dict with summary of actions taken.
    """
    if config is None:
        config = _load_consolidation_config(conn)

    results = {
        "short_to_mid_promoted": 0,
        "mid_to_long_promoted": 0,
        "contradictions_found": 0,
        "entries_decayed": 0,
        "entries_pruned": 0,
        "feedback_processed": 0,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Phase 1: Short-to-midterm consolidation
    stm_results = consolidate_short_to_mid(conn, config)
    results["short_to_mid_promoted"] = stm_results["promoted"]

    # Phase 1.5: Boost confidence of surviving midterm entries
    boost_results = boost_surviving_midterm(conn, config)
    results["confidence_boosted"] = boost_results["boosted"]

    # Phase 2: Midterm-to-long-term promotion
    mtl_results = promote_mid_to_long(conn, config)
    results["mid_to_long_promoted"] = mtl_results["promoted"]
    results["contradictions_found"] = mtl_results["contradictions"]

    # Phase 3: Decay and pruning
    decay_results = apply_decay_and_pruning(conn, config)
    results["entries_decayed"] = decay_results["decayed"]
    results["entries_pruned"] = decay_results["pruned"]

    # Phase 4: Feedback processing
    fb_results = process_feedback(conn, config)
    results["feedback_processed"] = fb_results["processed"]

    # Update last consolidation timestamp
    crud.set_config(conn, "last_consolidation_timestamp", results["timestamp"])

    return results


def consolidate_short_to_mid(conn, config=None):
    """
    Scan active short-term memories, cluster by semantic similarity,
    and promote clusters to midterm memory.

    Args:
        conn: sqlite3.Connection
        config: dict with clustering_similarity_threshold

    Returns:
        dict with 'promoted' count.
    """
    if config is None:
        config = _load_consolidation_config(conn)

    threshold = float(config.get("clustering_similarity_threshold", 0.85))
    promoted_count = 0

    # Get active STM entries that haven't expired
    rows = conn.execute(
        """SELECT id, content, embedding, timestamp, source, ttl_seconds
           FROM short_term_memory
           WHERE status = 'active' AND embedding IS NOT NULL"""
    ).fetchall()

    if not rows:
        return {"promoted": 0}

    entries = [dict(r) for r in rows]

    # Filter out expired entries
    now = datetime.utcnow()
    active_entries = []
    for entry in entries:
        created = datetime.fromisoformat(entry["timestamp"])
        ttl = timedelta(seconds=entry["ttl_seconds"])
        if now - created < ttl:
            active_entries.append(entry)
        else:
            # Mark as expired
            crud.update_short_term_memory(conn, entry["id"], status="expired")

    if not active_entries:
        return {"promoted": 0}

    # Cluster by semantic similarity
    clusters = _cluster_entries(active_entries, threshold)

    for cluster in clusters:
        if len(cluster) == 0:
            continue

        # Generate consolidated content
        contents = [e["content"] for e in cluster]
        if len(cluster) == 1:
            consolidated_text = contents[0]
        else:
            consolidated_text = " | ".join(contents)

        # Generate embedding for consolidated text
        emb = embedding_to_blob(generate_embedding(consolidated_text))

        # Calculate initial confidence based on cluster size and source diversity
        sources = set(e["source"] for e in cluster)
        confidence = min(0.3 + (len(cluster) * 0.1) + (len(sources) * 0.05), 0.9)

        source_ids = [e["id"] for e in cluster]

        # Create midterm entry
        mid_id = crud.create_midterm_memory(
            conn, consolidated_text, embedding=emb,
            confidence=confidence, source_ids=source_ids,
            category="observation",
        )

        # Mark STM entries as promoted
        for entry in cluster:
            crud.update_short_term_memory(conn, entry["id"], status="promoted")

        # Audit log
        crud.create_audit_entry(
            conn, "midterm_memory", mid_id, "promote", "consolidation",
            after_snapshot={"content": consolidated_text[:200], "source_count": len(cluster)},
        )

        promoted_count += 1

    return {"promoted": promoted_count}


def boost_surviving_midterm(conn, config=None):
    """
    Boost confidence of midterm entries that have survived across consolidation
    cycles. Entries gain confidence based on how many cycles they've survived
    (approximated by age in hours since creation).

    Boost formula:
        cycles_survived = hours_since_creation / consolidation_interval_hours
        boost = min(cycles_survived * 0.05, 0.3)
        new_confidence = min(confidence + boost, 0.95)

    This ensures memories that persist across multiple sleep cycles gradually
    climb toward the LTM promotion threshold (default 0.8), rewarding
    durability without requiring explicit endorsement.
    """
    if config is None:
        config = _load_consolidation_config(conn)

    # How often consolidation runs (default 5 min = 300s)
    interval_seconds = int(config.get("consolidation_interval_seconds",
                           crud.get_config_value(conn, "consolidation_interval_seconds", "300")))
    interval_hours = max(interval_seconds / 3600.0, 0.05)  # floor to avoid div-by-zero

    rows = conn.execute(
        "SELECT id, confidence, created_at FROM midterm_memory"
    ).fetchall()

    now = datetime.utcnow()
    boosted = 0

    for row in rows:
        created = datetime.fromisoformat(row["created_at"])
        hours_alive = (now - created).total_seconds() / 3600.0
        cycles_survived = hours_alive / interval_hours

        if cycles_survived < 1.0:
            continue  # Too new — hasn't survived a full cycle yet

        boost = min(cycles_survived * 0.05, 0.3)
        new_confidence = min(row["confidence"] + boost, 0.95)

        if new_confidence > row["confidence"]:
            crud.update_midterm_memory(conn, row["id"], confidence=round(new_confidence, 4))
            boosted += 1

    return {"boosted": boosted}


def promote_mid_to_long(conn, config=None):
    """
    Evaluate midterm entries above the promotion threshold.
    Check for contradictions against existing long-term memories.

    Args:
        conn: sqlite3.Connection
        config: dict with promotion_confidence_threshold

    Returns:
        dict with 'promoted' and 'contradictions' counts.
    """
    if config is None:
        config = _load_consolidation_config(conn)

    threshold = float(config.get("promotion_confidence_threshold", 0.8))
    promoted_count = 0
    contradiction_count = 0

    rows = conn.execute(
        """SELECT * FROM midterm_memory
           WHERE confidence >= ? AND embedding IS NOT NULL""",
        (threshold,),
    ).fetchall()

    if not rows:
        return {"promoted": 0, "contradictions": 0}

    # Load existing long-term memories for contradiction checking
    ltm_rows = conn.execute(
        "SELECT id, content, embedding FROM long_term_memory WHERE embedding IS NOT NULL"
    ).fetchall()
    ltm_entries = [(r["id"], r["embedding"]) for r in ltm_rows]

    for row in rows:
        entry = dict(row)
        entry_emb = entry["embedding"]

        # Check for contradictions against LTM
        has_contradiction = False
        if ltm_entries:
            similar = semantic_search(entry_emb, ltm_entries, top_k=3)
            for ltm_id, score in similar:
                # High similarity might indicate contradiction or reinforcement
                if score > 0.85:
                    # Flag as potential contradiction for review
                    crud.create_contradiction(
                        conn, entry["id"], "midterm_memory",
                        ltm_id, "long_term_memory",
                    )
                    # Create feedback entry for user review
                    crud.create_feedback(
                        conn, entry["id"], "midterm_memory",
                        "annotation",
                        f"High similarity ({score:.2f}) with LTM entry {ltm_id}. "
                        f"May be contradiction or reinforcement.",
                    )
                    has_contradiction = True
                    contradiction_count += 1
                    break

        if not has_contradiction:
            # Promote to long-term
            ltm_id = crud.create_long_term_memory(
                conn, entry["content"],
                embedding=entry_emb,
                confidence=entry["confidence"],
                provenance=entry.get("source_ids"),
                entity_ids=entry.get("entity_ids"),
                category=_infer_ltm_category(entry),
            )

            # Delete from midterm
            crud.delete_midterm_memory(conn, entry["id"])

            crud.create_audit_entry(
                conn, "long_term_memory", ltm_id, "promote", "consolidation",
                before_snapshot={"midterm_id": entry["id"]},
                after_snapshot={"content": entry["content"][:200]},
            )

            promoted_count += 1

    return {"promoted": promoted_count, "contradictions": contradiction_count}


def apply_decay_and_pruning(conn, config=None):
    """
    Apply time-based decay to midterm entries and prune those at zero.
    Flag stale long-term entries for revalidation.
    User-authored entries are exempt.

    Args:
        conn: sqlite3.Connection
        config: dict with decay_rate_multiplier, staleness_threshold_days

    Returns:
        dict with 'decayed' and 'pruned' counts.
    """
    if config is None:
        config = _load_consolidation_config(conn)

    if config.get("decay_enabled", "true") != "true":
        return {"decayed": 0, "pruned": 0}

    decay_multiplier = float(config.get("decay_rate_multiplier", 1.0))
    staleness_days = int(config.get("staleness_threshold_days", 90))

    decayed = 0
    pruned = 0

    # Decay midterm entries
    rows = conn.execute(
        "SELECT id, decay_weight, last_accessed FROM midterm_memory"
    ).fetchall()

    now = datetime.utcnow()
    for row in rows:
        last_accessed = datetime.fromisoformat(row["last_accessed"])
        days_since = (now - last_accessed).total_seconds() / 86400

        # Decay formula: reduce weight based on time since last access
        new_weight = max(0.0, row["decay_weight"] - (days_since * 0.01 * decay_multiplier))

        if new_weight != row["decay_weight"]:
            crud.update_midterm_memory(conn, row["id"], decay_weight=new_weight)
            decayed += 1

        if new_weight <= 0.0:
            crud.delete_midterm_memory(conn, row["id"])
            crud.create_audit_entry(
                conn, "midterm_memory", row["id"], "delete", "consolidation",
                before_snapshot={"decay_weight": 0.0},
            )
            pruned += 1

    # Flag stale long-term entries for revalidation (skip user-authored)
    staleness_cutoff = (now - timedelta(days=staleness_days)).isoformat()
    stale_rows = conn.execute(
        """SELECT id, content FROM long_term_memory
           WHERE last_validated < ?
           AND (provenance IS NULL OR provenance NOT LIKE '%user_authored%')""",
        (staleness_cutoff,),
    ).fetchall()

    for row in stale_rows:
        crud.create_feedback(
            conn, row["id"], "long_term_memory", "annotation",
            f"Stale entry (last validated > {staleness_days} days ago). Needs revalidation.",
        )

    return {"decayed": decayed, "pruned": pruned}


def process_feedback(conn, config=None):
    """
    Process unprocessed feedback entries.

    - Endorsements: increase confidence
    - Corrections: trigger contradiction flow
    - Deletion requests: queue for removal
    - Annotations: attach as relations

    Returns:
        dict with 'processed' count.
    """
    rows = conn.execute(
        "SELECT * FROM feedback WHERE processed = 0"
    ).fetchall()

    processed = 0
    for row in rows:
        entry = dict(row)
        target_id = entry["target_id"]
        target_table = entry["target_table"]
        fb_type = entry["feedback_type"]

        if fb_type == "endorsement":
            _apply_endorsement(conn, target_id, target_table)
        elif fb_type == "correction":
            _apply_correction(conn, target_id, target_table, entry["content"])
        elif fb_type == "deletion_request":
            _apply_deletion(conn, target_id, target_table)
        elif fb_type == "annotation":
            _apply_annotation(conn, entry["id"], target_id, target_table)

        crud.mark_feedback_processed(conn, entry["id"])
        processed += 1

    return {"processed": processed}


def _apply_endorsement(conn, target_id, target_table):
    """Increase the confidence of a memory."""
    if target_table == "midterm_memory":
        mem = crud.get_midterm_memory(conn, target_id)
        if mem:
            new_conf = min(1.0, mem["confidence"] + 0.1)
            crud.update_midterm_memory(conn, target_id, confidence=new_conf)
    elif target_table == "long_term_memory":
        mem = crud.get_long_term_memory(conn, target_id)
        if mem:
            new_conf = min(1.0, mem["confidence"] + 0.05)
            crud.update_long_term_memory(conn, target_id, confidence=new_conf)


def _apply_correction(conn, target_id, target_table, correction_content):
    """Log a contradiction for the correction."""
    # Create a temporary memory with the correction
    emb = embedding_to_blob(generate_embedding(correction_content))
    correction_id = crud.create_short_term_memory(
        conn, correction_content, "conversation", embedding=emb,
    )
    crud.create_contradiction(
        conn, target_id, target_table,
        correction_id, "short_term_memory",
    )


def _apply_deletion(conn, target_id, target_table):
    """Delete the target record."""
    if target_table == "short_term_memory":
        crud.delete_short_term_memory(conn, target_id)
    elif target_table == "midterm_memory":
        crud.delete_midterm_memory(conn, target_id)
    elif target_table == "long_term_memory":
        crud.delete_long_term_memory(conn, target_id)
    elif target_table == "skills":
        crud.delete_skill(conn, target_id)

    crud.create_audit_entry(
        conn, target_table, target_id, "delete", "user_feedback",
    )


def _apply_annotation(conn, feedback_id, target_id, target_table):
    """Create a relation linking the annotation to the target."""
    # Annotations are stored as feedback entries; we link via relations
    try:
        crud.create_relation(
            conn, feedback_id, "feedback",
            target_id, target_table,
            "related_to", weight=0.5,
            context="User annotation",
        )
    except Exception:
        # If the trigger blocks this (feedback not in content tables), skip silently
        pass


def _cluster_entries(entries, threshold):
    """
    Cluster entries by embedding cosine similarity using vectorized numpy ops.

    Assembles all embeddings into an N×D matrix, computes the full N×N
    similarity matrix via a single normalized dot-product, then applies
    greedy single-linkage clustering against the threshold.

    Args:
        entries: list of dicts with 'id', 'embedding', 'content' keys.
        threshold: float similarity threshold for clustering.

    Returns:
        list of lists of entry dicts.
    """
    import numpy as np

    if not entries:
        return []

    n = len(entries)
    if n == 1:
        return [entries]

    # Assemble N×D embedding matrix from blobs
    emb_list = [blob_to_embedding(e["embedding"]) for e in entries]
    matrix = np.stack(emb_list)  # (N, 384)

    # Normalize rows for cosine similarity via dot product
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    matrix_normed = matrix / norms

    # Full N×N similarity matrix in one matmul
    sim_matrix = matrix_normed @ matrix_normed.T  # (N, N)

    # Greedy single-linkage clustering on precomputed similarity
    assigned = set()
    clusters = []

    for i in range(n):
        if i in assigned:
            continue
        cluster_indices = [i]
        assigned.add(i)

        for j in range(i + 1, n):
            if j in assigned:
                continue
            if sim_matrix[i, j] >= threshold:
                cluster_indices.append(j)
                assigned.add(j)

        clusters.append([entries[idx] for idx in cluster_indices])

    return clusters


def _infer_ltm_category(midterm_entry):
    """Infer the long-term memory category from a midterm entry."""
    category = midterm_entry.get("category", "observation")
    if category == "pattern":
        return "relationship"
    if category == "inference":
        return "fact"
    return "fact"


def _load_consolidation_config(conn):
    """Load consolidation-related config from meta_config."""
    keys = [
        "clustering_similarity_threshold",
        "promotion_confidence_threshold",
        "decay_rate_multiplier",
        "staleness_threshold_days",
        "consolidation_enabled",
        "decay_enabled",
    ]
    config = {}
    for key in keys:
        val = crud.get_config_value(conn, key)
        if val is not None:
            config[key] = val
    return config


class ConsolidationScheduler:
    """
    Background scheduler that runs consolidation cycles at a configurable interval.
    """

    def __init__(self, db_path):
        self._db_path = db_path
        self._thread = None
        self._stop_event = threading.Event()
        self._last_result = None

    def start(self):
        """Start the consolidation scheduler in a background thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the consolidation scheduler."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)

    @property
    def last_result(self):
        return self._last_result

    def _run_loop(self):
        """Main loop: sleep for interval, then run consolidation."""
        from agentdb.database import get_connection

        while not self._stop_event.is_set():
            try:
                conn = get_connection(self._db_path)
                config = _load_consolidation_config(conn)

                if config.get("consolidation_enabled", "true") != "true":
                    conn.close()
                    self._stop_event.wait(60)
                    continue

                interval = int(crud.get_config_value(
                    conn, "consolidation_interval_seconds", "300"
                ))
                conn.close()

                # Wait for the interval
                if self._stop_event.wait(interval):
                    break

                # Run consolidation
                conn = get_connection(self._db_path)
                self._last_result = run_consolidation_cycle(conn)
                conn.close()

            except Exception as e:
                self._last_result = {"error": str(e)}
                self._stop_event.wait(60)
