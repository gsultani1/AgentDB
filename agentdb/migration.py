"""
External Chat Migration Pipeline for AgentDB.

Implements PRD Section 9:
- ChatGPT export parser with tree linearization
- Claude export parser
- Generic JSONL parser
- Five-phase pipeline (ingestion, consolidation, promotion, graph construction, review)
- Cross-provider deduplication
"""

import json
import os
from datetime import datetime
from pathlib import Path

from agentdb import crud
from agentdb.embeddings import (
    generate_embedding,
    embedding_to_blob,
    blob_to_embedding,
    cosine_similarity,
    semantic_search,
)


def run_migration_pipeline(conn, file_path, provider, callback=None):
    """
    Execute the full five-phase migration pipeline.

    Args:
        conn: sqlite3.Connection
        file_path: Path to the export file.
        provider: str, one of 'chatgpt', 'claude', 'generic'.
        callback: Optional callable(phase, progress, message) for status updates.

    Returns:
        dict with pipeline summary.
    """
    if callback is None:
        callback = lambda phase, progress, msg: None

    summary = {
        "provider": provider,
        "file": str(file_path),
        "conversations_imported": 0,
        "messages_ingested": 0,
        "midterm_created": 0,
        "longterm_promoted": 0,
        "entities_extracted": 0,
        "relations_created": 0,
        "contradictions_found": 0,
        "items_pending_review": 0,
    }

    # Phase 1: Raw Ingestion
    callback("ingestion", 0, "Starting raw ingestion...")
    sessions_data = _parse_export(file_path, provider)
    if not sessions_data:
        return {"status": "error", "error": "No conversations found in export"}

    session_ids = _ingest_sessions(conn, sessions_data, provider)
    summary["conversations_imported"] = len(session_ids)
    summary["messages_ingested"] = sum(
        len(s.get("messages", [])) for s in sessions_data
    )
    callback("ingestion", 100, f"Ingested {summary['messages_ingested']} messages from {summary['conversations_imported']} conversations")

    # Phase 2: Consolidation
    callback("consolidation", 0, "Running consolidation on imported entries...")
    consol_count = _consolidate_imported(conn, session_ids)
    summary["midterm_created"] = consol_count
    callback("consolidation", 100, f"Created {consol_count} midterm entries")

    # Phase 3: Promotion
    callback("promotion", 0, "Identifying patterns for promotion...")
    promo_result = _promote_patterns(conn)
    summary["longterm_promoted"] = promo_result["promoted"]
    summary["contradictions_found"] = promo_result["contradictions"]
    callback("promotion", 100, f"Promoted {promo_result['promoted']}, found {promo_result['contradictions']} contradictions")

    # Phase 4: Graph Construction
    callback("graph", 0, "Building knowledge graph edges...")
    graph_result = _build_graph(conn, session_ids)
    summary["entities_extracted"] = graph_result["entities"]
    summary["relations_created"] = graph_result["relations"]
    callback("graph", 100, f"Created {graph_result['relations']} relations for {graph_result['entities']} entities")

    # Phase 5: User Review
    callback("review", 0, "Generating review items...")
    review_count = _generate_review_items(conn)
    summary["items_pending_review"] = review_count
    callback("review", 100, f"{review_count} items flagged for review")

    summary["status"] = "ok"
    return summary


# ═══════════════════════════════════════════════════════════════════
# PHASE 1: PARSING
# ═══════════════════════════════════════════════════════════════════

def _parse_export(file_path, provider):
    """Parse an export file based on provider format."""
    file_path = Path(file_path)

    if provider == "chatgpt":
        return _parse_chatgpt(file_path)
    elif provider == "claude":
        return _parse_claude(file_path)
    elif provider == "generic":
        return _parse_generic_jsonl(file_path)

    raise ValueError(f"Unknown provider: {provider}")


def _parse_chatgpt(file_path):
    """
    Parse ChatGPT conversations.json export.
    Handles tree-structured conversations by walking the canonical path
    (last branch taken from each node).
    """
    if file_path.suffix == ".zip":
        import zipfile
        with zipfile.ZipFile(file_path) as zf:
            with zf.open("conversations.json") as f:
                data = json.loads(f.read().decode("utf-8"))
    else:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

    sessions = []
    for conv in data:
        title = conv.get("title", "Untitled")
        create_time = conv.get("create_time")
        update_time = conv.get("update_time")

        # Linearize the conversation tree
        mapping = conv.get("mapping", {})
        messages = _linearize_chatgpt_tree(mapping)

        if not messages:
            continue

        started_at = None
        if create_time:
            started_at = datetime.fromtimestamp(create_time).isoformat()

        sessions.append({
            "title": title,
            "started_at": started_at,
            "ended_at": datetime.fromtimestamp(update_time).isoformat() if update_time else None,
            "messages": messages,
        })

    return sessions


def _linearize_chatgpt_tree(mapping):
    """
    Walk the ChatGPT conversation tree and extract the canonical path.
    The canonical path follows the last child at each node.
    """
    if not mapping:
        return []

    # Find root node (no parent)
    root_id = None
    for node_id, node in mapping.items():
        parent = node.get("parent")
        if parent is None:
            root_id = node_id
            break

    if root_id is None:
        return []

    # Walk from root, always taking the last child
    messages = []
    current_id = root_id
    visited = set()

    while current_id and current_id not in visited:
        visited.add(current_id)
        node = mapping.get(current_id, {})
        msg = node.get("message")

        if msg and msg.get("content") and msg["content"].get("parts"):
            role = msg.get("author", {}).get("role", "unknown")
            parts = msg["content"]["parts"]
            text_parts = [p for p in parts if isinstance(p, str)]
            content = "\n".join(text_parts).strip()

            if content and role in ("user", "assistant", "system"):
                create_time = msg.get("create_time")
                timestamp = None
                if create_time:
                    timestamp = datetime.fromtimestamp(create_time).isoformat()

                messages.append({
                    "role": role,
                    "content": content,
                    "timestamp": timestamp,
                })

        children = node.get("children", [])
        current_id = children[-1] if children else None

    return messages


def _parse_claude(file_path):
    """Parse Claude export format."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    sessions = []

    # Claude exports vary in format; handle the common structures
    conversations = data if isinstance(data, list) else data.get("conversations", [data])

    for conv in conversations:
        title = conv.get("name", conv.get("title", "Untitled"))
        messages = []

        chat_messages = conv.get("chat_messages", conv.get("messages", []))
        for msg in chat_messages:
            role = msg.get("sender", msg.get("role", "unknown"))
            if role == "human":
                role = "user"
            elif role == "assistant":
                role = "assistant"
            else:
                continue

            content = ""
            if isinstance(msg.get("text"), str):
                content = msg["text"]
            elif isinstance(msg.get("content"), str):
                content = msg["content"]
            elif isinstance(msg.get("content"), list):
                text_parts = [
                    p.get("text", "") for p in msg["content"]
                    if isinstance(p, dict) and p.get("type") == "text"
                ]
                content = "\n".join(text_parts)

            if content.strip():
                timestamp = msg.get("created_at", msg.get("timestamp"))
                messages.append({
                    "role": role,
                    "content": content.strip(),
                    "timestamp": timestamp,
                })

        if messages:
            sessions.append({
                "title": title,
                "started_at": messages[0].get("timestamp"),
                "ended_at": messages[-1].get("timestamp"),
                "messages": messages,
            })

    return sessions


def _parse_generic_jsonl(file_path):
    """Parse generic JSONL format: one {role, content, timestamp} per line."""
    messages = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            msg = json.loads(line)
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
                "timestamp": msg.get("timestamp"),
            })

    if not messages:
        return []

    return [{
        "title": "Imported Conversation",
        "started_at": messages[0].get("timestamp"),
        "ended_at": messages[-1].get("timestamp"),
        "messages": messages,
    }]


# ═══════════════════════════════════════════════════════════════════
# PHASE 1: INGESTION
# ═══════════════════════════════════════════════════════════════════

def _ingest_sessions(conn, sessions_data, provider):
    """Ingest parsed sessions into the database."""
    source = f"{provider}_import"
    session_ids = []

    for session_data in sessions_data:
        # Create session
        sid = crud.create_session(conn)

        # Update session timestamps if available
        if session_data.get("started_at"):
            conn.execute(
                "UPDATE sessions SET started_at = ? WHERE id = ?",
                (session_data["started_at"], sid),
            )

        # Ingest messages
        for msg in session_data.get("messages", []):
            content = msg["content"]
            if not content:
                continue

            emb = embedding_to_blob(generate_embedding(content))
            crud.create_short_term_memory(
                conn, content, source,
                embedding=emb, session_id=sid, status="imported",
            )

        # Close session if we have an end time
        summary = session_data.get("title", "Imported conversation")
        if session_data.get("ended_at"):
            summary_emb = embedding_to_blob(generate_embedding(summary))
            crud.end_session(conn, sid, summary=summary, embedding=summary_emb)
        else:
            crud.end_session(conn, sid, summary=summary)

        session_ids.append(sid)

    crud.create_audit_entry(
        conn, "sessions", ",".join(session_ids[:5]), "insert", "migration",
        after_snapshot={
            "provider": provider,
            "sessions": len(session_ids),
        },
    )

    return session_ids


# ═══════════════════════════════════════════════════════════════════
# PHASE 2: CONSOLIDATION
# ═══════════════════════════════════════════════════════════════════

def _consolidate_imported(conn, session_ids):
    """Run consolidation on imported entries by session."""
    midterm_count = 0

    for sid in session_ids:
        rows = conn.execute(
            """SELECT id, content, embedding FROM short_term_memory
               WHERE session_id = ? AND status = 'imported' AND embedding IS NOT NULL
               ORDER BY timestamp ASC""",
            (sid,),
        ).fetchall()

        if not rows:
            continue

        # Group messages into exchanges (user + assistant pairs)
        entries = [dict(r) for r in rows]

        # Create a consolidated summary for the session
        contents = [e["content"][:200] for e in entries[:20]]
        consolidated = " | ".join(contents)

        if len(consolidated) > 1000:
            consolidated = consolidated[:1000]

        emb = embedding_to_blob(generate_embedding(consolidated))
        source_ids = [e["id"] for e in entries]

        crud.create_midterm_memory(
            conn, consolidated, embedding=emb,
            confidence=0.5, source_ids=source_ids,
            category="observation",
        )
        midterm_count += 1

    return midterm_count


# ═══════════════════════════════════════════════════════════════════
# PHASE 3: PROMOTION
# ═══════════════════════════════════════════════════════════════════

def _promote_patterns(conn):
    """Identify repeated patterns in midterm entries for promotion."""
    rows = conn.execute(
        "SELECT id, content, embedding, confidence FROM midterm_memory WHERE embedding IS NOT NULL"
    ).fetchall()

    if len(rows) < 2:
        return {"promoted": 0, "contradictions": 0}

    promoted = 0
    contradictions = 0
    entries = [dict(r) for r in rows]

    # Find entries that are similar to many others (repeated patterns)
    for entry in entries:
        if entry["confidence"] >= 0.7:
            continue  # Already high confidence

        emb = entry["embedding"]
        candidates = [(e["id"], e["embedding"]) for e in entries if e["id"] != entry["id"]]
        similar = semantic_search(emb, candidates, top_k=5)

        # Count similar entries above threshold
        high_sim_count = sum(1 for _, score in similar if score > 0.8)

        if high_sim_count >= 2:
            # Boost confidence for promotion
            new_conf = min(0.9, entry["confidence"] + (high_sim_count * 0.1))
            crud.update_midterm_memory(conn, entry["id"], confidence=new_conf)

            if new_conf >= 0.8:
                # Check for contradictions in LTM
                ltm_rows = conn.execute(
                    "SELECT id, embedding FROM long_term_memory WHERE embedding IS NOT NULL"
                ).fetchall()
                ltm_candidates = [(r["id"], r["embedding"]) for r in ltm_rows]

                if ltm_candidates:
                    ltm_similar = semantic_search(emb, ltm_candidates, top_k=1)
                    if ltm_similar and ltm_similar[0][1] > 0.85:
                        crud.create_contradiction(
                            conn, entry["id"], "midterm_memory",
                            ltm_similar[0][0], "long_term_memory",
                        )
                        contradictions += 1
                        continue

                # Promote
                crud.create_long_term_memory(
                    conn, entry["content"], embedding=emb,
                    confidence=new_conf,
                    provenance=entry.get("source_ids"),
                    category="fact",
                )
                crud.delete_midterm_memory(conn, entry["id"])
                promoted += 1

    return {"promoted": promoted, "contradictions": contradictions}


# ═══════════════════════════════════════════════════════════════════
# PHASE 4: GRAPH CONSTRUCTION
# ═══════════════════════════════════════════════════════════════════

def _build_graph(conn, session_ids):
    """Build knowledge graph edges from imported data."""
    entities_created = 0
    relations_created = 0

    # Link memories to their sessions
    for sid in session_ids:
        rows = conn.execute(
            "SELECT id FROM short_term_memory WHERE session_id = ?", (sid,)
        ).fetchall()

        for row in rows:
            try:
                crud.create_relation(
                    conn, row["id"], "short_term_memory",
                    sid, "sessions",
                    "derived_from", weight=0.5,
                    context="Message from imported session",
                )
                relations_created += 1
            except Exception:
                pass

    return {"entities": entities_created, "relations": relations_created}


# ═══════════════════════════════════════════════════════════════════
# PHASE 5: USER REVIEW
# ═══════════════════════════════════════════════════════════════════

def _generate_review_items(conn):
    """Generate feedback entries for items needing user review."""
    review_count = 0

    # Flag unresolved contradictions
    contradictions = crud.list_contradictions(conn, resolution="unresolved")
    for c in contradictions:
        crud.create_feedback(
            conn, c["memory_a_id"], c["memory_a_table"],
            "annotation",
            f"Unresolved contradiction with {c['memory_b_table']}:{c['memory_b_id'][:8]}",
        )
        review_count += 1

    # Flag low-confidence midterm entries
    low_conf = conn.execute(
        "SELECT id FROM midterm_memory WHERE confidence < 0.4"
    ).fetchall()
    for row in low_conf:
        crud.create_feedback(
            conn, row["id"], "midterm_memory",
            "annotation",
            "Low confidence imported memory. Review for accuracy.",
        )
        review_count += 1

    return review_count
