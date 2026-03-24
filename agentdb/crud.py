"""
Data access module for AgentDB.

Provides CRUD operations for all 23 tables. Each function accepts a
sqlite3.Connection as its first argument and returns dict-ified rows
via sqlite3.Row.
"""

import json
import uuid
from datetime import datetime


def _new_id():
    """Generate a new UUID4 string."""
    return str(uuid.uuid4())


def _now():
    """UTC timestamp in ISO format."""
    return datetime.utcnow().isoformat()


def _row_to_dict(row):
    """Convert a sqlite3.Row to a plain dict."""
    if row is None:
        return None
    return dict(row)


def _rows_to_list(rows):
    """Convert a list of sqlite3.Row objects to a list of dicts."""
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════
# SHORT-TERM MEMORY
# ═══════════════════════════════════════════════════════════════════

def create_short_term_memory(conn, content, source, embedding=None,
                             ttl_seconds=3600, session_id=None, status="active",
                             agent_id="default"):
    """Insert a new short-term memory entry."""
    mid = _new_id()
    conn.execute(
        """INSERT INTO short_term_memory
           (id, agent_id, timestamp, source, content, embedding, ttl_seconds, session_id, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (mid, agent_id, _now(), source, content, embedding, ttl_seconds, session_id, status),
    )
    conn.commit()
    return mid


def get_short_term_memory(conn, mid):
    """Retrieve a single short-term memory by ID."""
    row = conn.execute(
        "SELECT * FROM short_term_memory WHERE id = ?", (mid,)
    ).fetchone()
    return _row_to_dict(row)


def list_short_term_memories(conn, status=None, session_id=None,
                             agent_id=None, limit=100, offset=0):
    """List short-term memories with optional filters. agent_id scopes to that agent + 'shared'."""
    query = "SELECT * FROM short_term_memory WHERE 1=1"
    params = []
    if agent_id:
        query += " AND (agent_id = ? OR agent_id = 'shared')"
        params.append(agent_id)
    if status:
        query += " AND status = ?"
        params.append(status)
    if session_id:
        query += " AND session_id = ?"
        params.append(session_id)
    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return _rows_to_list(conn.execute(query, params).fetchall())


def update_short_term_memory(conn, mid, **kwargs):
    """Update fields on a short-term memory entry."""
    allowed = {"content", "embedding", "ttl_seconds", "status", "session_id", "source"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [mid]
    conn.execute(
        f"UPDATE short_term_memory SET {set_clause} WHERE id = ?", values
    )
    conn.commit()
    return True


def delete_short_term_memory(conn, mid):
    """Delete a short-term memory entry."""
    conn.execute("DELETE FROM short_term_memory WHERE id = ?", (mid,))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
# MIDTERM MEMORY
# ═══════════════════════════════════════════════════════════════════

def create_midterm_memory(conn, content, embedding=None, confidence=0.5,
                          source_ids=None, entity_ids=None, decay_weight=1.0,
                          category="observation", agent_id="default"):
    """Insert a new midterm memory entry."""
    mid = _new_id()
    conn.execute(
        """INSERT INTO midterm_memory
           (id, agent_id, created_at, last_accessed, content, embedding, confidence,
            source_ids, entity_ids, decay_weight, category)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (mid, agent_id, _now(), _now(), content, embedding, confidence,
         json.dumps(source_ids) if source_ids else None,
         json.dumps(entity_ids) if entity_ids else None,
         decay_weight, category),
    )
    conn.commit()
    return mid


def get_midterm_memory(conn, mid):
    """Retrieve a single midterm memory by ID."""
    row = conn.execute(
        "SELECT * FROM midterm_memory WHERE id = ?", (mid,)
    ).fetchone()
    return _row_to_dict(row)


def list_midterm_memories(conn, category=None, min_confidence=None,
                          agent_id=None, limit=100, offset=0):
    """List midterm memories with optional filters. agent_id scopes to that agent + 'shared'."""
    query = "SELECT * FROM midterm_memory WHERE 1=1"
    params = []
    if agent_id:
        query += " AND (agent_id = ? OR agent_id = 'shared')"
        params.append(agent_id)
    if category:
        query += " AND category = ?"
        params.append(category)
    if min_confidence is not None:
        query += " AND confidence >= ?"
        params.append(min_confidence)
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return _rows_to_list(conn.execute(query, params).fetchall())


def update_midterm_memory(conn, mid, **kwargs):
    """Update fields on a midterm memory entry."""
    allowed = {"content", "embedding", "confidence", "source_ids", "entity_ids",
               "decay_weight", "category", "last_accessed"}
    updates = {}
    for k, v in kwargs.items():
        if k not in allowed:
            continue
        if k in ("source_ids", "entity_ids") and isinstance(v, (list, dict)):
            v = json.dumps(v)
        updates[k] = v
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [mid]
    conn.execute(
        f"UPDATE midterm_memory SET {set_clause} WHERE id = ?", values
    )
    conn.commit()
    return True


def delete_midterm_memory(conn, mid):
    """Delete a midterm memory entry."""
    conn.execute("DELETE FROM midterm_memory WHERE id = ?", (mid,))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
# LONG-TERM MEMORY
# ═══════════════════════════════════════════════════════════════════

def create_long_term_memory(conn, content, embedding=None, confidence=0.9,
                            provenance=None, entity_ids=None, category="fact",
                            agent_id="default"):
    """Insert a new long-term memory entry."""
    mid = _new_id()
    conn.execute(
        """INSERT INTO long_term_memory
           (id, agent_id, created_at, last_validated, content, embedding, confidence,
            provenance, entity_ids, category)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (mid, agent_id, _now(), _now(), content, embedding, confidence,
         json.dumps(provenance) if provenance else None,
         json.dumps(entity_ids) if entity_ids else None,
         category),
    )
    conn.commit()
    return mid


def get_long_term_memory(conn, mid):
    """Retrieve a single long-term memory by ID."""
    row = conn.execute(
        "SELECT * FROM long_term_memory WHERE id = ?", (mid,)
    ).fetchone()
    return _row_to_dict(row)


def list_long_term_memories(conn, category=None, min_confidence=None,
                            agent_id=None, limit=100, offset=0):
    """List long-term memories with optional filters. agent_id scopes to that agent + 'shared'."""
    query = "SELECT * FROM long_term_memory WHERE 1=1"
    params = []
    if agent_id:
        query += " AND (agent_id = ? OR agent_id = 'shared')"
        params.append(agent_id)
    if category:
        query += " AND category = ?"
        params.append(category)
    if min_confidence is not None:
        query += " AND confidence >= ?"
        params.append(min_confidence)
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return _rows_to_list(conn.execute(query, params).fetchall())


def update_long_term_memory(conn, mid, **kwargs):
    """Update fields on a long-term memory entry."""
    allowed = {"content", "embedding", "confidence", "provenance", "entity_ids",
               "category", "last_validated"}
    updates = {}
    for k, v in kwargs.items():
        if k not in allowed:
            continue
        if k in ("provenance", "entity_ids") and isinstance(v, (list, dict)):
            v = json.dumps(v)
        updates[k] = v
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [mid]
    conn.execute(
        f"UPDATE long_term_memory SET {set_clause} WHERE id = ?", values
    )
    conn.commit()
    return True


def delete_long_term_memory(conn, mid):
    """Delete a long-term memory entry."""
    conn.execute("DELETE FROM long_term_memory WHERE id = ?", (mid,))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
# SKILLS
# ═══════════════════════════════════════════════════════════════════

def create_skill(conn, name, description, execution_type, embedding=None,
                 input_schema=None, output_schema=None):
    """Insert a new skill."""
    sid = _new_id()
    conn.execute(
        """INSERT INTO skills
           (id, name, description, embedding, input_schema, output_schema,
            version, created_at, use_count, success_rate, execution_type)
           VALUES (?, ?, ?, ?, ?, ?, 1, ?, 0, 0.0, ?)""",
        (sid, name, description, embedding,
         json.dumps(input_schema) if input_schema else None,
         json.dumps(output_schema) if output_schema else None,
         _now(), execution_type),
    )
    conn.commit()
    return sid


def get_skill(conn, sid):
    """Retrieve a single skill by ID."""
    row = conn.execute("SELECT * FROM skills WHERE id = ?", (sid,)).fetchone()
    return _row_to_dict(row)


def list_skills(conn, execution_type=None, limit=100, offset=0):
    """List skills with optional filters."""
    query = "SELECT * FROM skills WHERE 1=1"
    params = []
    if execution_type:
        query += " AND execution_type = ?"
        params.append(execution_type)
    query += " ORDER BY name ASC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return _rows_to_list(conn.execute(query, params).fetchall())


def update_skill(conn, sid, **kwargs):
    """Update fields on a skill."""
    allowed = {"name", "description", "embedding", "input_schema", "output_schema",
               "version", "last_used", "use_count", "success_rate", "execution_type"}
    updates = {}
    for k, v in kwargs.items():
        if k not in allowed:
            continue
        if k in ("input_schema", "output_schema") and isinstance(v, (list, dict)):
            v = json.dumps(v)
        updates[k] = v
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [sid]
    conn.execute(f"UPDATE skills SET {set_clause} WHERE id = ?", values)
    conn.commit()
    return True


def delete_skill(conn, sid):
    """Delete a skill and its implementations (via cascade trigger)."""
    conn.execute("DELETE FROM skills WHERE id = ?", (sid,))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
# SKILL IMPLEMENTATIONS
# ═══════════════════════════════════════════════════════════════════

def create_skill_implementation(conn, skill_id, version, language, code,
                                content_hash, dependencies=None,
                                is_active=False, execution_order=None):
    """Insert a new skill implementation version."""
    iid = _new_id()
    conn.execute(
        """INSERT INTO skill_implementations
           (id, skill_id, version, language, code, content_hash,
            dependencies, created_at, is_active, execution_order)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (iid, skill_id, version, language, code, content_hash,
         json.dumps(dependencies) if dependencies else None,
         _now(), int(is_active), execution_order),
    )
    conn.commit()
    return iid


def get_skill_implementation(conn, iid):
    """Retrieve a single skill implementation by ID."""
    row = conn.execute(
        "SELECT * FROM skill_implementations WHERE id = ?", (iid,)
    ).fetchone()
    return _row_to_dict(row)


def list_skill_implementations(conn, skill_id, active_only=False):
    """List all implementations for a skill."""
    query = "SELECT * FROM skill_implementations WHERE skill_id = ?"
    params = [skill_id]
    if active_only:
        query += " AND is_active = 1"
    query += " ORDER BY version DESC"
    return _rows_to_list(conn.execute(query, params).fetchall())


def activate_skill_implementation(conn, iid, skill_id):
    """Set one implementation as active, deactivating all others for the skill."""
    conn.execute(
        "UPDATE skill_implementations SET is_active = 0 WHERE skill_id = ?",
        (skill_id,),
    )
    conn.execute(
        "UPDATE skill_implementations SET is_active = 1 WHERE id = ?",
        (iid,),
    )
    conn.commit()


def delete_skill_implementation(conn, iid):
    """Delete a single skill implementation."""
    conn.execute("DELETE FROM skill_implementations WHERE id = ?", (iid,))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
# RELATIONS
# ═══════════════════════════════════════════════════════════════════

def create_relation(conn, source_id, source_table, target_id, target_table,
                    edge_type, weight=1.0, context=None):
    """Insert a new relation edge."""
    rid = _new_id()
    conn.execute(
        """INSERT INTO relations
           (id, source_id, source_table, target_id, target_table,
            edge_type, weight, created_at, context)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (rid, source_id, source_table, target_id, target_table,
         edge_type, weight, _now(), context),
    )
    conn.commit()
    return rid


def get_relation(conn, rid):
    """Retrieve a single relation by ID."""
    row = conn.execute("SELECT * FROM relations WHERE id = ?", (rid,)).fetchone()
    return _row_to_dict(row)


def list_relations_for_node(conn, node_id, node_table=None):
    """List all relations where node_id is source or target."""
    if node_table:
        rows = conn.execute(
            """SELECT * FROM relations
               WHERE (source_id = ? AND source_table = ?)
                  OR (target_id = ? AND target_table = ?)
               ORDER BY weight DESC""",
            (node_id, node_table, node_id, node_table),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM relations
               WHERE source_id = ? OR target_id = ?
               ORDER BY weight DESC""",
            (node_id, node_id),
        ).fetchall()
    return _rows_to_list(rows)


def update_relation(conn, rid, **kwargs):
    """Update fields on a relation."""
    allowed = {"edge_type", "weight", "context"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [rid]
    conn.execute(f"UPDATE relations SET {set_clause} WHERE id = ?", values)
    conn.commit()
    return True


def delete_relation(conn, rid):
    """Delete a relation edge."""
    conn.execute("DELETE FROM relations WHERE id = ?", (rid,))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
# ENTITIES
# ═══════════════════════════════════════════════════════════════════

def create_entity(conn, canonical_name, entity_type, embedding=None, aliases=None):
    """Insert a new entity."""
    eid = _new_id()
    now = _now()
    conn.execute(
        """INSERT INTO entities
           (id, canonical_name, entity_type, embedding, first_seen, last_seen, aliases)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (eid, canonical_name, entity_type, embedding, now, now,
         json.dumps(aliases) if aliases else None),
    )
    conn.commit()
    return eid


def get_entity(conn, eid):
    """Retrieve a single entity by ID."""
    row = conn.execute("SELECT * FROM entities WHERE id = ?", (eid,)).fetchone()
    return _row_to_dict(row)


def find_entity_by_name(conn, name):
    """Find entities by canonical name or alias (case-insensitive)."""
    rows = conn.execute(
        """SELECT * FROM entities
           WHERE LOWER(canonical_name) = LOWER(?)
              OR LOWER(aliases) LIKE LOWER(?)""",
        (name, f'%"{name}"%'),
    ).fetchall()
    return _rows_to_list(rows)


def list_entities(conn, entity_type=None, limit=100, offset=0):
    """List entities with optional type filter."""
    query = "SELECT * FROM entities WHERE 1=1"
    params = []
    if entity_type:
        query += " AND entity_type = ?"
        params.append(entity_type)
    query += " ORDER BY canonical_name ASC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return _rows_to_list(conn.execute(query, params).fetchall())


def update_entity(conn, eid, **kwargs):
    """Update fields on an entity."""
    allowed = {"canonical_name", "entity_type", "embedding", "last_seen", "aliases"}
    updates = {}
    for k, v in kwargs.items():
        if k not in allowed:
            continue
        if k == "aliases" and isinstance(v, list):
            v = json.dumps(v)
        updates[k] = v
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [eid]
    conn.execute(f"UPDATE entities SET {set_clause} WHERE id = ?", values)
    conn.commit()
    return True


def delete_entity(conn, eid):
    """Delete an entity."""
    conn.execute("DELETE FROM entities WHERE id = ?", (eid,))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
# GOALS
# ═══════════════════════════════════════════════════════════════════

def create_goal(conn, description, embedding=None, priority=0,
                deadline=None, parent_goal_id=None):
    """Insert a new goal."""
    gid = _new_id()
    conn.execute(
        """INSERT INTO goals
           (id, description, embedding, priority, status, created_at,
            deadline, parent_goal_id, completed_at)
           VALUES (?, ?, ?, ?, 'active', ?, ?, ?, NULL)""",
        (gid, description, embedding, priority, _now(), deadline, parent_goal_id),
    )
    conn.commit()
    return gid


def get_goal(conn, gid):
    """Retrieve a single goal by ID."""
    row = conn.execute("SELECT * FROM goals WHERE id = ?", (gid,)).fetchone()
    return _row_to_dict(row)


def list_goals(conn, status=None, limit=100, offset=0):
    """List goals with optional status filter."""
    query = "SELECT * FROM goals WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY priority DESC, created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return _rows_to_list(conn.execute(query, params).fetchall())


def update_goal(conn, gid, **kwargs):
    """Update fields on a goal."""
    allowed = {"description", "embedding", "priority", "status",
               "deadline", "parent_goal_id", "completed_at"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [gid]
    conn.execute(f"UPDATE goals SET {set_clause} WHERE id = ?", values)
    conn.commit()
    return True


def delete_goal(conn, gid):
    """Delete a goal."""
    conn.execute("DELETE FROM goals WHERE id = ?", (gid,))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
# TAGS
# ═══════════════════════════════════════════════════════════════════

def create_tag(conn, name, color=None):
    """Insert a new tag."""
    tid = _new_id()
    conn.execute(
        "INSERT INTO tags (id, name, color) VALUES (?, ?, ?)",
        (tid, name, color),
    )
    conn.commit()
    return tid


def get_tag(conn, tid):
    """Retrieve a single tag by ID."""
    row = conn.execute("SELECT * FROM tags WHERE id = ?", (tid,)).fetchone()
    return _row_to_dict(row)


def find_tag_by_name(conn, name):
    """Find a tag by name."""
    row = conn.execute("SELECT * FROM tags WHERE name = ?", (name,)).fetchone()
    return _row_to_dict(row)


def list_tags(conn):
    """List all tags."""
    return _rows_to_list(
        conn.execute("SELECT * FROM tags ORDER BY name ASC").fetchall()
    )


def update_tag(conn, tid, **kwargs):
    """Update fields on a tag."""
    allowed = {"name", "color"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [tid]
    conn.execute(f"UPDATE tags SET {set_clause} WHERE id = ?", values)
    conn.commit()
    return True


def delete_tag(conn, tid):
    """Delete a tag (cascade trigger removes assignments)."""
    conn.execute("DELETE FROM tags WHERE id = ?", (tid,))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
# TAG ASSIGNMENTS
# ═══════════════════════════════════════════════════════════════════

def create_tag_assignment(conn, tag_id, target_id, target_table):
    """Assign a tag to a record."""
    aid = _new_id()
    conn.execute(
        """INSERT INTO tag_assignments (id, tag_id, target_id, target_table)
           VALUES (?, ?, ?, ?)""",
        (aid, tag_id, target_id, target_table),
    )
    conn.commit()
    return aid


def list_tag_assignments_for_target(conn, target_id, target_table):
    """List all tags assigned to a specific record."""
    return _rows_to_list(conn.execute(
        """SELECT ta.*, t.name AS tag_name, t.color AS tag_color
           FROM tag_assignments ta
           JOIN tags t ON t.id = ta.tag_id
           WHERE ta.target_id = ? AND ta.target_table = ?""",
        (target_id, target_table),
    ).fetchall())


def list_tag_assignments_for_tag(conn, tag_id):
    """List all records assigned a specific tag."""
    return _rows_to_list(conn.execute(
        "SELECT * FROM tag_assignments WHERE tag_id = ?", (tag_id,)
    ).fetchall())


def delete_tag_assignment(conn, aid):
    """Remove a tag assignment."""
    conn.execute("DELETE FROM tag_assignments WHERE id = ?", (aid,))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
# WORKSPACES
# ═══════════════════════════════════════════════════════════════════

def create_workspace(conn, name, root_path, workspace_type, metadata=None):
    """Register a new workspace."""
    wid = _new_id()
    conn.execute(
        """INSERT INTO workspaces
           (id, name, root_path, workspace_type, created_at, metadata)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (wid, name, root_path, workspace_type, _now(),
         json.dumps(metadata) if metadata else None),
    )
    conn.commit()
    return wid


def get_workspace(conn, wid):
    """Retrieve a single workspace by ID."""
    row = conn.execute(
        "SELECT * FROM workspaces WHERE id = ?", (wid,)
    ).fetchone()
    return _row_to_dict(row)


def list_workspaces(conn):
    """List all registered workspaces."""
    return _rows_to_list(
        conn.execute("SELECT * FROM workspaces ORDER BY name ASC").fetchall()
    )


def update_workspace(conn, wid, **kwargs):
    """Update fields on a workspace."""
    allowed = {"name", "root_path", "workspace_type", "last_scanned", "metadata"}
    updates = {}
    for k, v in kwargs.items():
        if k not in allowed:
            continue
        if k == "metadata" and isinstance(v, dict):
            v = json.dumps(v)
        updates[k] = v
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [wid]
    conn.execute(f"UPDATE workspaces SET {set_clause} WHERE id = ?", values)
    conn.commit()
    return True


def delete_workspace(conn, wid):
    """Delete a workspace (cascade trigger removes files)."""
    conn.execute("DELETE FROM workspaces WHERE id = ?", (wid,))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
# WORKSPACE FILES
# ═══════════════════════════════════════════════════════════════════

def create_workspace_file(conn, workspace_id, relative_path, file_type,
                          depth=0, size_bytes=None, file_last_modified=None,
                          content_hash=None, embedding=None, summary=None):
    """Register a file within a workspace."""
    fid = _new_id()
    conn.execute(
        """INSERT INTO workspace_files
           (id, workspace_id, relative_path, file_type, depth, size_bytes,
            file_last_modified, last_scanned, content_hash, embedding, summary)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (fid, workspace_id, relative_path, file_type, depth, size_bytes,
         file_last_modified, _now(), content_hash, embedding, summary),
    )
    conn.commit()
    return fid


def get_workspace_file(conn, fid):
    """Retrieve a single workspace file by ID."""
    row = conn.execute(
        "SELECT * FROM workspace_files WHERE id = ?", (fid,)
    ).fetchone()
    return _row_to_dict(row)


def list_workspace_files(conn, workspace_id, file_type=None, limit=500, offset=0):
    """List files in a workspace."""
    query = "SELECT * FROM workspace_files WHERE workspace_id = ?"
    params = [workspace_id]
    if file_type:
        query += " AND file_type = ?"
        params.append(file_type)
    query += " ORDER BY relative_path ASC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return _rows_to_list(conn.execute(query, params).fetchall())


def update_workspace_file(conn, fid, **kwargs):
    """Update fields on a workspace file."""
    allowed = {"file_type", "size_bytes", "file_last_modified", "last_scanned",
               "content_hash", "embedding", "summary"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [fid]
    conn.execute(
        f"UPDATE workspace_files SET {set_clause} WHERE id = ?", values
    )
    conn.commit()
    return True


def delete_workspace_file(conn, fid):
    """Delete a workspace file record."""
    conn.execute("DELETE FROM workspace_files WHERE id = ?", (fid,))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
# SESSIONS
# ═══════════════════════════════════════════════════════════════════

def create_session(conn, workspace_id=None, thread_id=None, provider_id=None):
    """Start a new session, optionally linked to a conversation thread."""
    sid = _new_id()
    conn.execute(
        """INSERT INTO sessions
           (id, started_at, status, workspace_id, thread_id, provider_id)
           VALUES (?, ?, 'active', ?, ?, ?)""",
        (sid, _now(), workspace_id, thread_id, provider_id),
    )
    conn.commit()
    # Update thread last_active if linked
    if thread_id:
        conn.execute(
            "UPDATE conversation_threads SET last_active = ? WHERE id = ?",
            (_now(), thread_id),
        )
        conn.commit()
    return sid


def get_session(conn, sid):
    """Retrieve a single session by ID."""
    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
    return _row_to_dict(row)


def list_sessions(conn, status=None, limit=100, offset=0):
    """List sessions with optional status filter."""
    query = "SELECT * FROM sessions WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return _rows_to_list(conn.execute(query, params).fetchall())


def end_session(conn, sid, summary=None, embedding=None):
    """Close a session with optional summary."""
    conn.execute(
        """UPDATE sessions
           SET ended_at = ?, summary = ?, embedding = ?, status = 'closed'
           WHERE id = ?""",
        (_now(), summary, embedding, sid),
    )
    conn.commit()


def delete_session(conn, sid):
    """Delete a session."""
    conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
# SCHEDULED TASKS
# ═══════════════════════════════════════════════════════════════════

def _scheduled_task_row_to_dict(row):
    """Convert a scheduled task row to a dict and decode JSON fields."""
    task = _row_to_dict(row)
    if task is None:
        return None
    for key in ("payload_json", "last_result_json"):
        value = task.get(key)
        if not value:
            continue
        try:
            task[key] = json.loads(value)
        except (TypeError, ValueError):
            pass
    return task


def _scheduled_task_rows_to_list(rows):
    """Convert a list of scheduled task rows to decoded dicts."""
    return [_scheduled_task_row_to_dict(r) for r in rows]


def create_scheduled_task(conn, name, action_type, interval_seconds,
                          next_run_at, description=None, agent_id="default",
                          schedule_type="interval", payload_json=None,
                          status="active"):
    """Create a scheduled task."""
    tid = _new_id()
    conn.execute(
        """INSERT INTO scheduled_tasks
           (id, name, description, agent_id, action_type, schedule_type,
            interval_seconds, payload_json, status, next_run_at,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            tid, name, description, agent_id, action_type, schedule_type,
            interval_seconds,
            json.dumps(payload_json) if isinstance(payload_json, (dict, list)) else payload_json,
            status, next_run_at, _now(), _now(),
        ),
    )
    conn.commit()
    return tid


def get_scheduled_task(conn, task_id):
    """Retrieve a single scheduled task by ID."""
    row = conn.execute(
        "SELECT * FROM scheduled_tasks WHERE id = ?", (task_id,)
    ).fetchone()
    return _scheduled_task_row_to_dict(row)


def list_scheduled_tasks(conn, status=None, agent_id=None, limit=100, offset=0):
    """List scheduled tasks with optional filters."""
    query = "SELECT * FROM scheduled_tasks WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if agent_id:
        query += " AND agent_id = ?"
        params.append(agent_id)
    query += " ORDER BY next_run_at ASC, created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(query, params).fetchall()
    return _scheduled_task_rows_to_list(rows)


def list_due_scheduled_tasks(conn, now=None, limit=20):
    """List active scheduled tasks due to run."""
    now = now or _now()
    rows = conn.execute(
        """SELECT * FROM scheduled_tasks
           WHERE status = 'active' AND next_run_at <= ?
           ORDER BY next_run_at ASC LIMIT ?""",
        (now, limit),
    ).fetchall()
    return _scheduled_task_rows_to_list(rows)


def update_scheduled_task(conn, task_id, **kwargs):
    """Update fields on a scheduled task."""
    allowed = {
        "name", "description", "agent_id", "action_type", "schedule_type",
        "interval_seconds", "payload_json", "status", "next_run_at",
        "last_run_at", "last_result_json", "last_error",
    }
    updates = {}
    for k, v in kwargs.items():
        if k not in allowed:
            continue
        if k in ("payload_json", "last_result_json") and isinstance(v, (dict, list)):
            v = json.dumps(v)
        updates[k] = v
    if not updates:
        return False
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [task_id]
    conn.execute(
        f"UPDATE scheduled_tasks SET {set_clause} WHERE id = ?", values
    )
    conn.commit()
    return True


def record_scheduled_task_success(conn, task_id, last_run_at, next_run_at,
                                  result=None, status="active"):
    """Record a successful scheduled task run."""
    return update_scheduled_task(
        conn,
        task_id,
        last_run_at=last_run_at,
        next_run_at=next_run_at,
        last_result_json=result,
        last_error=None,
        status=status,
    )


def record_scheduled_task_failure(conn, task_id, last_run_at, error,
                                  status="error"):
    """Record a failed scheduled task run."""
    return update_scheduled_task(
        conn,
        task_id,
        last_run_at=last_run_at,
        last_error=str(error),
        status=status,
    )


def delete_scheduled_task(conn, task_id):
    """Delete a scheduled task."""
    conn.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
# META CONFIG
# ═══════════════════════════════════════════════════════════════════

def get_config(conn, key):
    """Get a single config value by key."""
    row = conn.execute(
        "SELECT * FROM meta_config WHERE key = ?", (key,)
    ).fetchone()
    return _row_to_dict(row)


def get_config_value(conn, key, default=None):
    """Get just the value string for a config key."""
    row = conn.execute(
        "SELECT value FROM meta_config WHERE key = ?", (key,)
    ).fetchone()
    if row is None:
        return default
    return row["value"]


def list_config(conn):
    """List all config entries."""
    return _rows_to_list(
        conn.execute("SELECT * FROM meta_config ORDER BY key ASC").fetchall()
    )


def set_config(conn, key, value):
    """Set a config value (insert or update)."""
    existing = conn.execute(
        "SELECT id FROM meta_config WHERE key = ?", (key,)
    ).fetchone()
    now = _now()
    if existing:
        conn.execute(
            "UPDATE meta_config SET value = ?, updated_at = ? WHERE key = ?",
            (value, now, key),
        )
    else:
        conn.execute(
            "INSERT INTO meta_config (id, key, value, updated_at) VALUES (?, ?, ?, ?)",
            (_new_id(), key, value, now),
        )
    conn.commit()


def delete_config(conn, key):
    """Delete a config entry."""
    conn.execute("DELETE FROM meta_config WHERE key = ?", (key,))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
# CONTRADICTIONS
# ═══════════════════════════════════════════════════════════════════

def create_contradiction(conn, memory_a_id, memory_a_table,
                         memory_b_id, memory_b_table):
    """Log a contradiction between two memories."""
    cid = _new_id()
    conn.execute(
        """INSERT INTO contradictions
           (id, memory_a_id, memory_a_table, memory_b_id, memory_b_table,
            resolution, reasoning, resolved_at, resolved_by)
           VALUES (?, ?, ?, ?, ?, 'unresolved', NULL, NULL, NULL)""",
        (cid, memory_a_id, memory_a_table, memory_b_id, memory_b_table),
    )
    conn.commit()
    return cid


def get_contradiction(conn, cid):
    """Retrieve a single contradiction by ID."""
    row = conn.execute(
        "SELECT * FROM contradictions WHERE id = ?", (cid,)
    ).fetchone()
    return _row_to_dict(row)


def list_contradictions(conn, resolution=None, limit=100, offset=0):
    """List contradictions with optional resolution filter."""
    query = "SELECT * FROM contradictions WHERE 1=1"
    params = []
    if resolution:
        query += " AND resolution = ?"
        params.append(resolution)
    query += " ORDER BY rowid DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return _rows_to_list(conn.execute(query, params).fetchall())


def resolve_contradiction(conn, cid, resolution, reasoning, resolved_by="user"):
    """Resolve a contradiction."""
    conn.execute(
        """UPDATE contradictions
           SET resolution = ?, reasoning = ?, resolved_at = ?, resolved_by = ?
           WHERE id = ?""",
        (resolution, reasoning, _now(), resolved_by, cid),
    )
    conn.commit()


def delete_contradiction(conn, cid):
    """Delete a contradiction record."""
    conn.execute("DELETE FROM contradictions WHERE id = ?", (cid,))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
# AUDIT LOG
# ═══════════════════════════════════════════════════════════════════

def create_audit_entry(conn, table_name, row_id, operation, triggered_by,
                       before_snapshot=None, after_snapshot=None):
    """Insert an audit log entry."""
    aid = _new_id()
    conn.execute(
        """INSERT INTO audit_log
           (id, timestamp, table_name, row_id, operation,
            before_snapshot, after_snapshot, triggered_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (aid, _now(), table_name, row_id, operation,
         json.dumps(before_snapshot) if before_snapshot else None,
         json.dumps(after_snapshot) if after_snapshot else None,
         triggered_by),
    )
    conn.commit()
    return aid


def list_audit_entries(conn, table_name=None, operation=None,
                       triggered_by=None, limit=100, offset=0):
    """List audit log entries with optional filters."""
    query = "SELECT * FROM audit_log WHERE 1=1"
    params = []
    if table_name:
        query += " AND table_name = ?"
        params.append(table_name)
    if operation:
        query += " AND operation = ?"
        params.append(operation)
    if triggered_by:
        query += " AND triggered_by = ?"
        params.append(triggered_by)
    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return _rows_to_list(conn.execute(query, params).fetchall())


# ═══════════════════════════════════════════════════════════════════
# FEEDBACK
# ═══════════════════════════════════════════════════════════════════

def create_feedback(conn, target_id, target_table, feedback_type, content):
    """Submit feedback on a memory or skill."""
    fid = _new_id()
    conn.execute(
        """INSERT INTO feedback
           (id, target_id, target_table, feedback_type, content, created_at, processed)
           VALUES (?, ?, ?, ?, ?, ?, 0)""",
        (fid, target_id, target_table, feedback_type, content, _now()),
    )
    conn.commit()
    return fid


def get_feedback(conn, fid):
    """Retrieve a single feedback entry by ID."""
    row = conn.execute("SELECT * FROM feedback WHERE id = ?", (fid,)).fetchone()
    return _row_to_dict(row)


def list_feedback(conn, target_id=None, target_table=None,
                  processed=None, limit=100, offset=0):
    """List feedback entries with optional filters."""
    query = "SELECT * FROM feedback WHERE 1=1"
    params = []
    if target_id:
        query += " AND target_id = ?"
        params.append(target_id)
    if target_table:
        query += " AND target_table = ?"
        params.append(target_table)
    if processed is not None:
        query += " AND processed = ?"
        params.append(int(processed))
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return _rows_to_list(conn.execute(query, params).fetchall())


def mark_feedback_processed(conn, fid):
    """Mark a feedback entry as processed."""
    conn.execute("UPDATE feedback SET processed = 1 WHERE id = ?", (fid,))
    conn.commit()


def delete_feedback(conn, fid):
    """Delete a feedback entry."""
    conn.execute("DELETE FROM feedback WHERE id = ?", (fid,))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
# CONTEXT SNAPSHOTS
# ═══════════════════════════════════════════════════════════════════

def create_context_snapshot(conn, trigger_description, memory_ids=None,
                            skill_ids=None, relation_ids=None,
                            goal_id=None, outcome=None):
    """Capture a context snapshot."""
    sid = _new_id()
    conn.execute(
        """INSERT INTO context_snapshots
           (id, timestamp, trigger_description, memory_ids, skill_ids,
            relation_ids, goal_id, outcome)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (sid, _now(), trigger_description,
         json.dumps(memory_ids) if memory_ids else None,
         json.dumps(skill_ids) if skill_ids else None,
         json.dumps(relation_ids) if relation_ids else None,
         goal_id, outcome),
    )
    conn.commit()
    return sid


def get_context_snapshot(conn, sid):
    """Retrieve a single context snapshot by ID."""
    row = conn.execute(
        "SELECT * FROM context_snapshots WHERE id = ?", (sid,)
    ).fetchone()
    return _row_to_dict(row)


def list_context_snapshots(conn, goal_id=None, limit=100, offset=0):
    """List context snapshots with optional goal filter."""
    query = "SELECT * FROM context_snapshots WHERE 1=1"
    params = []
    if goal_id:
        query += " AND goal_id = ?"
        params.append(goal_id)
    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return _rows_to_list(conn.execute(query, params).fetchall())


def delete_context_snapshot(conn, sid):
    """Delete a context snapshot."""
    conn.execute("DELETE FROM context_snapshots WHERE id = ?", (sid,))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
# VIEWS
# ═══════════════════════════════════════════════════════════════════

def create_view(conn, name, center_node_id, center_node_table,
                depth_limit=2, filters=None, layout_hints=None):
    """Save a new graph view."""
    vid = _new_id()
    conn.execute(
        """INSERT INTO views
           (id, name, center_node_id, center_node_table,
            depth_limit, filters, layout_hints)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (vid, name, center_node_id, center_node_table, depth_limit,
         json.dumps(filters) if filters else None,
         json.dumps(layout_hints) if layout_hints else None),
    )
    conn.commit()
    return vid


def get_view(conn, vid):
    """Retrieve a single view by ID."""
    row = conn.execute("SELECT * FROM views WHERE id = ?", (vid,)).fetchone()
    return _row_to_dict(row)


def list_views(conn):
    """List all saved views."""
    return _rows_to_list(
        conn.execute("SELECT * FROM views ORDER BY name ASC").fetchall()
    )


def update_view(conn, vid, **kwargs):
    """Update fields on a view."""
    allowed = {"name", "center_node_id", "center_node_table",
               "depth_limit", "filters", "layout_hints"}
    updates = {}
    for k, v in kwargs.items():
        if k not in allowed:
            continue
        if k in ("filters", "layout_hints") and isinstance(v, dict):
            v = json.dumps(v)
        updates[k] = v
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [vid]
    conn.execute(f"UPDATE views SET {set_clause} WHERE id = ?", values)
    conn.commit()
    return True


def delete_view(conn, vid):
    """Delete a saved view."""
    conn.execute("DELETE FROM views WHERE id = ?", (vid,))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
# EMBEDDINGS CACHE
# ═══════════════════════════════════════════════════════════════════

def create_embeddings_cache_entry(conn, node_a_id, node_a_table,
                                  node_b_id, node_b_table, similarity_score):
    """Store a precomputed similarity score."""
    eid = _new_id()
    conn.execute(
        """INSERT INTO embeddings_cache
           (id, node_a_id, node_a_table, node_b_id, node_b_table,
            similarity_score, computed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (eid, node_a_id, node_a_table, node_b_id, node_b_table,
         similarity_score, _now()),
    )
    conn.commit()
    return eid


def get_cached_similarity(conn, node_a_id, node_a_table, node_b_id, node_b_table):
    """Look up a cached similarity score between two nodes."""
    row = conn.execute(
        """SELECT similarity_score, computed_at FROM embeddings_cache
           WHERE (node_a_id = ? AND node_a_table = ? AND node_b_id = ? AND node_b_table = ?)
              OR (node_a_id = ? AND node_a_table = ? AND node_b_id = ? AND node_b_table = ?)""",
        (node_a_id, node_a_table, node_b_id, node_b_table,
         node_b_id, node_b_table, node_a_id, node_a_table),
    ).fetchone()
    return _row_to_dict(row)


def clear_embeddings_cache(conn):
    """Clear the entire embeddings cache."""
    conn.execute("DELETE FROM embeddings_cache")
    conn.commit()


# ═══════════════════════════════════════════════════════════════
# AGENTS
# ═══════════════════════════════════════════════════════════════

def create_agent(conn, agent_id, name, description=None, config=None):
    """Register a new agent."""
    conn.execute(
        """INSERT INTO agents (id, name, description, created_at, config)
           VALUES (?, ?, ?, ?, ?)""",
        (agent_id, name, description, _now(),
         json.dumps(config) if config else None),
    )
    conn.commit()
    return agent_id


def get_agent(conn, agent_id):
    """Retrieve a single agent by ID."""
    row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    return _row_to_dict(row)


def list_agents(conn):
    """List all registered agents."""
    return _rows_to_list(
        conn.execute("SELECT * FROM agents ORDER BY created_at ASC").fetchall()
    )


def update_agent(conn, agent_id, **kwargs):
    """Update fields on an agent."""
    allowed = {"name", "description", "last_active", "config"}
    updates = {}
    for k, v in kwargs.items():
        if k not in allowed:
            continue
        if k == "config" and isinstance(v, dict):
            v = json.dumps(v)
        updates[k] = v
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [agent_id]
    conn.execute(f"UPDATE agents SET {set_clause} WHERE id = ?", values)
    conn.commit()
    return True


def touch_agent_activity(conn, agent_id):
    """Update last_active timestamp for an agent."""
    conn.execute(
        "UPDATE agents SET last_active = ? WHERE id = ?",
        (_now(), agent_id),
    )
    conn.commit()


def delete_agent(conn, agent_id):
    """Delete an agent."""
    conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
    conn.commit()


# ═══════════════════════════════════════════════════════════════
# NOTIFICATION QUEUE
# ═══════════════════════════════════════════════════════════════

def create_notification(conn, title, trigger_type, agent_id="default",
                        body=None, priority="medium", related_ids=None):
    """Create a new notification."""
    nid = _new_id()
    conn.execute(
        """INSERT INTO notification_queue
           (id, agent_id, trigger_type, title, body, priority, related_ids, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (nid, agent_id, trigger_type, title, body, priority,
         json.dumps(related_ids) if related_ids else None, _now()),
    )
    conn.commit()
    return nid


def get_notification(conn, nid):
    """Retrieve a single notification by ID."""
    row = conn.execute(
        "SELECT * FROM notification_queue WHERE id = ?", (nid,)
    ).fetchone()
    return _row_to_dict(row)


def list_notifications(conn, read=None, priority=None, agent_id=None,
                       trigger_type=None, limit=100, offset=0):
    """List notifications with optional filters."""
    query = "SELECT * FROM notification_queue WHERE 1=1"
    params = []
    if read is not None:
        query += " AND read = ?"
        params.append(int(read))
    if priority:
        query += " AND priority = ?"
        params.append(priority)
    if agent_id:
        query += " AND agent_id = ?"
        params.append(agent_id)
    if trigger_type:
        query += " AND trigger_type = ?"
        params.append(trigger_type)
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return _rows_to_list(conn.execute(query, params).fetchall())


def mark_notification_read(conn, nid):
    """Mark a notification as read."""
    conn.execute(
        "UPDATE notification_queue SET read = 1 WHERE id = ?", (nid,)
    )
    conn.commit()


def mark_notification_delivered(conn, nid):
    """Mark a notification as delivered."""
    conn.execute(
        "UPDATE notification_queue SET delivered = 1 WHERE id = ?", (nid,)
    )
    conn.commit()


def dismiss_read_notifications(conn):
    """Delete all read notifications."""
    conn.execute("DELETE FROM notification_queue WHERE read = 1")
    conn.commit()


def count_unread_notifications(conn, agent_id=None):
    """Count unread notifications."""
    query = "SELECT COUNT(*) FROM notification_queue WHERE read = 0"
    params = []
    if agent_id:
        query += " AND agent_id = ?"
        params.append(agent_id)
    return conn.execute(query, params).fetchone()[0]


# ── LLM Providers ──

def list_llm_providers(conn, limit=50):
    rows = conn.execute("SELECT * FROM llm_providers ORDER BY is_default DESC, name ASC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]

def get_llm_provider(conn, provider_id):
    row = conn.execute("SELECT * FROM llm_providers WHERE id = ?", (provider_id,)).fetchone()
    return dict(row) if row else None

def get_default_llm_provider(conn):
    row = conn.execute("SELECT * FROM llm_providers WHERE is_default = 1 LIMIT 1").fetchone()
    return dict(row) if row else None

def _sync_default_provider_to_config(conn):
    """Keep meta_config flat keys in sync with the current default provider."""
    row = conn.execute(
        "SELECT provider_type, api_key, model, endpoint FROM llm_providers WHERE is_default = 1 LIMIT 1"
    ).fetchone()
    if row:
        row = dict(row) if hasattr(row, 'keys') else {
            'provider_type': row[0], 'api_key': row[1], 'model': row[2], 'endpoint': row[3]
        }
        now = _now()
        for cfg_key, prov_key in [
            ("llm_provider", "provider_type"),
            ("llm_api_key", "api_key"),
            ("llm_model", "model"),
            ("llm_endpoint", "endpoint"),
        ]:
            val = row.get(prov_key, "") or ""
            conn.execute(
                "UPDATE meta_config SET value = ?, updated_at = ? WHERE key = ?",
                (val, now, cfg_key),
            )
        conn.commit()


def create_llm_provider(conn, name, provider_type, model, api_key='', endpoint='', is_default=False):
    pid = str(uuid.uuid4())
    if is_default:
        conn.execute("UPDATE llm_providers SET is_default = 0")
    conn.execute(
        "INSERT INTO llm_providers (id, name, provider_type, api_key, model, endpoint, is_default) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (pid, name, provider_type, api_key, model, endpoint, 1 if is_default else 0))
    conn.commit()
    if is_default:
        _sync_default_provider_to_config(conn)
    return pid

def update_llm_provider(conn, provider_id, **kwargs):
    if kwargs.get('is_default'):
        conn.execute("UPDATE llm_providers SET is_default = 0")
    sets, vals = [], []
    for k, v in kwargs.items():
        if v is not None:
            sets.append(f"{k} = ?")
            vals.append(1 if k == 'is_default' and v else (0 if k == 'is_default' else v))
    if not sets:
        return
    vals.append(provider_id)
    conn.execute(f"UPDATE llm_providers SET {', '.join(sets)} WHERE id = ?", vals)
    conn.commit()
    # Sync if this provider is now or was already the default
    row = conn.execute(
        "SELECT is_default FROM llm_providers WHERE id = ?", (provider_id,)
    ).fetchone()
    if row and (row[0] or kwargs.get('is_default')):
        _sync_default_provider_to_config(conn)

def delete_llm_provider(conn, provider_id):
    conn.execute("DELETE FROM llm_providers WHERE id = ?", (provider_id,))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
# CONVERSATION THREADS
# ═══════════════════════════════════════════════════════════════════

def create_conversation_thread(conn, name, agent_id="default", provider_id=None,
                                summary=None, metadata=None):
    """Create a new conversation thread."""
    tid = _new_id()
    now = _now()
    conn.execute(
        """INSERT INTO conversation_threads
           (id, name, agent_id, provider_id, created_at, last_active, summary, status, pinned, metadata)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 0, ?)""",
        (tid, name, agent_id, provider_id, now, now, summary,
         json.dumps(metadata) if metadata else None),
    )
    conn.commit()
    return tid


def get_conversation_thread(conn, tid):
    row = conn.execute("SELECT * FROM conversation_threads WHERE id = ?", (tid,)).fetchone()
    return _row_to_dict(row)


def list_conversation_threads(conn, agent_id=None, status=None, limit=100, offset=0):
    query = "SELECT * FROM conversation_threads WHERE 1=1"
    params = []
    if agent_id:
        query += " AND agent_id = ?"
        params.append(agent_id)
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY pinned DESC, last_active DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return _rows_to_list(conn.execute(query, params).fetchall())


def update_conversation_thread(conn, tid, **kwargs):
    sets, vals = [], []
    for k, v in kwargs.items():
        if v is not None:
            sets.append(f"{k} = ?")
            vals.append(json.dumps(v) if k == 'metadata' else v)
    if not sets:
        return
    vals.append(tid)
    conn.execute(f"UPDATE conversation_threads SET {', '.join(sets)} WHERE id = ?", vals)
    conn.commit()


def delete_conversation_thread(conn, tid):
    conn.execute("DELETE FROM conversation_threads WHERE id = ?", (tid,))
    conn.commit()


def get_thread_messages(conn, thread_id, limit=100, offset=0):
    """Get all short-term memories (messages) for a thread via its sessions."""
    rows = conn.execute(
        """SELECT stm.* FROM short_term_memory stm
           JOIN sessions s ON stm.session_id = s.id
           WHERE s.thread_id = ?
           ORDER BY stm.timestamp ASC LIMIT ? OFFSET ?""",
        (thread_id, limit, offset),
    ).fetchall()
    return _rows_to_list(rows)


# ═══════════════════════════════════════════════════════════════════
# PINNED MEMORIES
# ═══════════════════════════════════════════════════════════════════

def pin_memory(conn, memory_id, memory_table, agent_id=None, label=None,
               priority=0, pinned_by="user"):
    """Pin a memory so it always appears in context."""
    pid = _new_id()
    conn.execute(
        """INSERT INTO pinned_memories
           (id, memory_id, memory_table, agent_id, pinned_at, pinned_by, label, priority)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (pid, memory_id, memory_table, agent_id, _now(), pinned_by, label, priority),
    )
    conn.commit()
    return pid


def unpin_memory(conn, pin_id):
    """Remove a memory pin."""
    conn.execute("DELETE FROM pinned_memories WHERE id = ?", (pin_id,))
    conn.commit()


def list_pinned_memories(conn, agent_id=None):
    """List all pinned memories, optionally scoped by agent."""
    query = "SELECT * FROM pinned_memories WHERE 1=1"
    params = []
    if agent_id:
        query += " AND (agent_id = ? OR agent_id IS NULL)"
        params.append(agent_id)
    query += " ORDER BY priority ASC"
    return _rows_to_list(conn.execute(query, params).fetchall())


def get_pinned_memory_contents(conn, agent_id=None):
    """Get the actual memory content for all pinned memories."""
    pins = list_pinned_memories(conn, agent_id)
    results = []
    for pin in pins:
        table = pin["memory_table"]
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?",
                           (pin["memory_id"],)).fetchone()
        if row:
            entry = dict(row)
            entry["pin_id"] = pin["id"]
            entry["pin_label"] = pin["label"]
            entry["pin_priority"] = pin["priority"]
            entry["tier"] = table.replace("_memory", "").replace("short_term", "short_term").replace("midterm", "midterm").replace("long_term", "long_term")
            entry.pop("embedding", None)
            results.append(entry)
    return results


def update_pin_priority(conn, pin_id, priority):
    conn.execute("UPDATE pinned_memories SET priority = ? WHERE id = ?", (priority, pin_id))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
# FILE ATTACHMENTS
# ═══════════════════════════════════════════════════════════════════

def create_file_attachment(conn, filename, session_id=None, thread_id=None,
                           mime_type=None, size_bytes=None, extraction_method=None,
                           extracted_text=None, extracted_embedding=None,
                           chunk_count=0, stm_ids=None, retained_path=None):
    aid = _new_id()
    conn.execute(
        """INSERT INTO file_attachments
           (id, session_id, thread_id, filename, mime_type, size_bytes,
            extraction_method, extracted_text, extracted_embedding,
            chunk_count, stm_ids, uploaded_at, retained_path)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (aid, session_id, thread_id, filename, mime_type, size_bytes,
         extraction_method, extracted_text, extracted_embedding,
         chunk_count, json.dumps(stm_ids) if stm_ids else None, _now(), retained_path),
    )
    conn.commit()
    return aid


def get_file_attachment(conn, aid):
    row = conn.execute("SELECT * FROM file_attachments WHERE id = ?", (aid,)).fetchone()
    return _row_to_dict(row)


def list_file_attachments(conn, session_id=None, thread_id=None, limit=100, offset=0):
    query = "SELECT * FROM file_attachments WHERE 1=1"
    params = []
    if session_id:
        query += " AND session_id = ?"
        params.append(session_id)
    if thread_id:
        query += " AND thread_id = ?"
        params.append(thread_id)
    query += " ORDER BY uploaded_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return _rows_to_list(conn.execute(query, params).fetchall())


# ═══════════════════════════════════════════════════════════════════
# SKILL EXECUTIONS
# ═══════════════════════════════════════════════════════════════════

def create_skill_execution(conn, skill_id, agent_id="default", session_id=None,
                           implementation_id=None, inputs=None):
    eid = _new_id()
    conn.execute(
        """INSERT INTO skill_executions
           (id, skill_id, implementation_id, agent_id, session_id, started_at, status, inputs)
           VALUES (?, ?, ?, ?, ?, ?, 'running', ?)""",
        (eid, skill_id, implementation_id, agent_id, session_id, _now(),
         json.dumps(inputs) if inputs else None),
    )
    conn.commit()
    return eid


def complete_skill_execution(conn, exec_id, status, outputs=None, stdout=None,
                              stderr=None, exit_code=None, resource_usage=None):
    now = _now()
    # Calculate duration
    row = conn.execute("SELECT started_at FROM skill_executions WHERE id = ?",
                       (exec_id,)).fetchone()
    duration_ms = None
    if row:
        from datetime import datetime as dt
        try:
            started = dt.fromisoformat(row[0])
            duration_ms = int((dt.fromisoformat(now) - started).total_seconds() * 1000)
        except (ValueError, TypeError):
            pass
    conn.execute(
        """UPDATE skill_executions
           SET status = ?, completed_at = ?, duration_ms = ?, outputs = ?,
               stdout = ?, stderr = ?, exit_code = ?, resource_usage = ?
           WHERE id = ?""",
        (status, now, duration_ms,
         json.dumps(outputs) if outputs else None,
         stdout, stderr, exit_code,
         json.dumps(resource_usage) if resource_usage else None,
         exec_id),
    )
    conn.commit()


def list_skill_executions(conn, skill_id=None, agent_id=None, status=None,
                          limit=100, offset=0):
    query = "SELECT * FROM skill_executions WHERE 1=1"
    params = []
    if skill_id:
        query += " AND skill_id = ?"
        params.append(skill_id)
    if agent_id:
        query += " AND agent_id = ?"
        params.append(agent_id)
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return _rows_to_list(conn.execute(query, params).fetchall())


def get_skill_execution(conn, exec_id):
    row = conn.execute("SELECT * FROM skill_executions WHERE id = ?",
                       (exec_id,)).fetchone()
    return _row_to_dict(row)


# ═══════════════════════════════════════════════════════════════════
# CHANNEL CONFIGS
# ═══════════════════════════════════════════════════════════════════

def create_channel_config(conn, name, channel_type, config, agent_id="default",
                           authorized_senders=None, polling_interval_seconds=60,
                           is_default_notification=False):
    cid = _new_id()
    now = _now()
    conn.execute(
        """INSERT INTO channel_configs
           (id, name, channel_type, config, authorized_senders, agent_id,
            is_active, is_default_notification, polling_interval_seconds,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)""",
        (cid, name, channel_type,
         json.dumps(config) if isinstance(config, dict) else config,
         json.dumps(authorized_senders) if authorized_senders else None,
         agent_id, 1 if is_default_notification else 0,
         polling_interval_seconds, now, now),
    )
    conn.commit()
    return cid


def get_channel_config(conn, cid):
    row = conn.execute("SELECT * FROM channel_configs WHERE id = ?", (cid,)).fetchone()
    return _row_to_dict(row)


def list_channel_configs(conn, channel_type=None, agent_id=None, active_only=True):
    query = "SELECT * FROM channel_configs WHERE 1=1"
    params = []
    if active_only:
        query += " AND is_active = 1"
    if channel_type:
        query += " AND channel_type = ?"
        params.append(channel_type)
    if agent_id:
        query += " AND agent_id = ?"
        params.append(agent_id)
    query += " ORDER BY name"
    return _rows_to_list(conn.execute(query, params).fetchall())


def update_channel_config(conn, cid, **kwargs):
    sets, vals = [], []
    for k, v in kwargs.items():
        if v is not None:
            sets.append(f"{k} = ?")
            vals.append(json.dumps(v) if k in ('config', 'authorized_senders') and isinstance(v, (dict, list)) else v)
    if not sets:
        return
    sets.append("updated_at = ?")
    vals.append(_now())
    vals.append(cid)
    conn.execute(f"UPDATE channel_configs SET {', '.join(sets)} WHERE id = ?", vals)
    conn.commit()


def delete_channel_config(conn, cid):
    conn.execute("DELETE FROM channel_configs WHERE id = ?", (cid,))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
# CHANNEL MESSAGES
# ═══════════════════════════════════════════════════════════════════

def create_channel_message(conn, channel_id, direction, content, sender=None,
                           recipient=None, raw_payload=None, session_id=None,
                           task_id=None, status="delivered"):
    mid = _new_id()
    conn.execute(
        """INSERT INTO channel_messages
           (id, channel_id, direction, sender, recipient, content,
            raw_payload, session_id, task_id, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (mid, channel_id, direction, sender, recipient, content,
         json.dumps(raw_payload) if raw_payload else None,
         session_id, task_id, status, _now()),
    )
    conn.commit()
    return mid


def list_channel_messages(conn, channel_id, limit=100, offset=0):
    return _rows_to_list(conn.execute(
        """SELECT * FROM channel_messages WHERE channel_id = ?
           ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (channel_id, limit, offset),
    ).fetchall())


# ═══════════════════════════════════════════════════════════════════
# AUTONOMOUS TASKS
# ═══════════════════════════════════════════════════════════════════

def create_autonomous_task(conn, title, goal, agent_id="default", provider_id=None,
                           max_iterations=50, max_duration_minutes=60,
                           require_approval=False, notification_channel_id=None,
                           creation_channel="ui"):
    tid = _new_id()
    now = _now()
    conn.execute(
        """INSERT INTO autonomous_tasks
           (id, title, goal, agent_id, provider_id, status, max_iterations,
            max_duration_minutes, require_approval, notification_channel_id,
            creation_channel, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)""",
        (tid, title, goal, agent_id, provider_id, max_iterations,
         max_duration_minutes, 1 if require_approval else 0,
         notification_channel_id, creation_channel, now, now),
    )
    conn.commit()
    return tid


def get_autonomous_task(conn, tid):
    row = conn.execute("SELECT * FROM autonomous_tasks WHERE id = ?", (tid,)).fetchone()
    return _row_to_dict(row)


def list_autonomous_tasks(conn, status=None, agent_id=None, limit=100, offset=0):
    query = "SELECT * FROM autonomous_tasks WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if agent_id:
        query += " AND agent_id = ?"
        params.append(agent_id)
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return _rows_to_list(conn.execute(query, params).fetchall())


def update_autonomous_task(conn, tid, **kwargs):
    sets, vals = [], []
    for k, v in kwargs.items():
        if v is not None:
            sets.append(f"{k} = ?")
            vals.append(json.dumps(v) if k == 'plan' else v)
    if not sets:
        return
    sets.append("updated_at = ?")
    vals.append(_now())
    vals.append(tid)
    conn.execute(f"UPDATE autonomous_tasks SET {', '.join(sets)} WHERE id = ?", vals)
    conn.commit()


def delete_autonomous_task(conn, tid):
    conn.execute("DELETE FROM autonomous_tasks WHERE id = ?", (tid,))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
# TASK STEPS
# ═══════════════════════════════════════════════════════════════════

def create_task_step(conn, task_id, step_number, description, llm_reasoning=None):
    sid = _new_id()
    conn.execute(
        """INSERT INTO task_steps
           (id, task_id, step_number, description, status, llm_reasoning, created_at)
           VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
        (sid, task_id, step_number, description, llm_reasoning, _now()),
    )
    conn.commit()
    return sid


def update_task_step(conn, step_id, **kwargs):
    sets, vals = [], []
    for k, v in kwargs.items():
        if v is not None:
            sets.append(f"{k} = ?")
            vals.append(json.dumps(v) if k == 'result' else v)
    if not sets:
        return
    vals.append(step_id)
    conn.execute(f"UPDATE task_steps SET {', '.join(sets)} WHERE id = ?", vals)
    conn.commit()


def list_task_steps(conn, task_id):
    return _rows_to_list(conn.execute(
        "SELECT * FROM task_steps WHERE task_id = ? ORDER BY step_number",
        (task_id,),
    ).fetchall())


# ═══════════════════════════════════════════════════════════════════
# TASK ACTIONS
# ═══════════════════════════════════════════════════════════════════

def create_task_action(conn, task_id, action_type, step_id=None, inputs=None):
    aid = _new_id()
    conn.execute(
        """INSERT INTO task_actions
           (id, task_id, step_id, action_type, inputs, status, created_at)
           VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
        (aid, task_id, step_id, action_type,
         json.dumps(inputs) if inputs else None, _now()),
    )
    conn.commit()
    return aid


def complete_task_action(conn, action_id, status, outputs=None, error=None,
                          duration_ms=None):
    conn.execute(
        """UPDATE task_actions
           SET status = ?, outputs = ?, error = ?, duration_ms = ?
           WHERE id = ?""",
        (status, json.dumps(outputs) if outputs else None,
         error, duration_ms, action_id),
    )
    conn.commit()


def list_task_actions(conn, task_id, step_id=None, limit=100, offset=0):
    query = "SELECT * FROM task_actions WHERE task_id = ?"
    params = [task_id]
    if step_id:
        query += " AND step_id = ?"
        params.append(step_id)
    query += " ORDER BY created_at ASC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return _rows_to_list(conn.execute(query, params).fetchall())


# ═══════════════════════════════════════════════════════════════════
# FILE ACCESS GRANTS
# ═══════════════════════════════════════════════════════════════════

def create_file_access_grant(conn, directory_path, agent_id="default",
                              permission="read", notes=None):
    gid = _new_id()
    conn.execute(
        """INSERT INTO file_access_grants
           (id, agent_id, directory_path, permission, granted_at, granted_by, notes)
           VALUES (?, ?, ?, ?, ?, 'operator', ?)""",
        (gid, agent_id, directory_path, permission, _now(), notes),
    )
    conn.commit()
    return gid


def list_file_access_grants(conn, agent_id=None):
    query = "SELECT * FROM file_access_grants WHERE 1=1"
    params = []
    if agent_id:
        query += " AND agent_id = ?"
        params.append(agent_id)
    query += " ORDER BY granted_at DESC"
    return _rows_to_list(conn.execute(query, params).fetchall())


def delete_file_access_grant(conn, gid):
    conn.execute("DELETE FROM file_access_grants WHERE id = ?", (gid,))
    conn.commit()


def check_file_access(conn, agent_id, file_path, require_write=False):
    """Check if an agent has access to a given file path."""
    grants = list_file_access_grants(conn, agent_id)
    import os
    file_path = os.path.abspath(file_path)
    for grant in grants:
        grant_path = os.path.abspath(grant["directory_path"])
        if file_path.startswith(grant_path):
            if require_write and grant["permission"] != "read_write":
                continue
            return True
    return False


# ═══════════════════════════════════════════════════════════════════
# SHELL COMMAND LOG
# ═══════════════════════════════════════════════════════════════════

def create_shell_command_log(conn, command, agent_id="default", task_id=None,
                              working_dir=None):
    lid = _new_id()
    conn.execute(
        """INSERT INTO shell_command_log
           (id, agent_id, task_id, command, working_dir, started_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (lid, agent_id, task_id, command, working_dir, _now()),
    )
    conn.commit()
    return lid


def complete_shell_command_log(conn, log_id, stdout=None, stderr=None,
                                exit_code=None, duration_ms=None):
    conn.execute(
        """UPDATE shell_command_log
           SET stdout = ?, stderr = ?, exit_code = ?, duration_ms = ?,
               completed_at = ?
           WHERE id = ?""",
        (stdout, stderr, exit_code, duration_ms, _now(), log_id),
    )
    conn.commit()


def list_shell_command_log(conn, agent_id=None, task_id=None, limit=100, offset=0):
    query = "SELECT * FROM shell_command_log WHERE 1=1"
    params = []
    if agent_id:
        query += " AND agent_id = ?"
        params.append(agent_id)
    if task_id:
        query += " AND task_id = ?"
        params.append(task_id)
    query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return _rows_to_list(conn.execute(query, params).fetchall())


# ═══════════════════════════════════════════════════════════════════
# MEMORY EXPORT
# ═══════════════════════════════════════════════════════════════════

def export_memories(conn, tier="all", agent_id=None, format="json",
                    include_embeddings=False, filters=None):
    """Export memories in the requested format."""
    if filters is None:
        filters = {}
    tables = {
        "short": "short_term_memory",
        "mid": "midterm_memory",
        "long": "long_term_memory",
    }
    if tier == "all":
        tiers_to_export = list(tables.keys())
    else:
        tiers_to_export = [tier] if tier in tables else list(tables.keys())

    results = []
    for t in tiers_to_export:
        table = tables[t]
        query = f"SELECT * FROM {table} WHERE 1=1"
        params = []
        if agent_id:
            query += " AND (agent_id = ? OR agent_id = 'shared')"
            params.append(agent_id)
        if filters.get("confidence_min") and t != "short":
            query += " AND confidence >= ?"
            params.append(float(filters["confidence_min"]))
        if filters.get("category") and t != "short":
            query += " AND category = ?"
            params.append(filters["category"])
        query += " ORDER BY " + ("timestamp" if t == "short" else "created_at") + " DESC"
        rows = conn.execute(query, params).fetchall()
        for row in rows:
            entry = dict(row)
            entry["tier"] = t
            if not include_embeddings:
                entry.pop("embedding", None)
            results.append(entry)
    return results


# ═══════════════════════════════════════════════════════════════════
# BATCH MEMORY OPERATIONS
# ═══════════════════════════════════════════════════════════════════

def batch_pin_memories(conn, memory_ids_with_tables, agent_id=None, label=None):
    """Pin multiple memories at once. memory_ids_with_tables: list of (id, table)."""
    pin_ids = []
    for memory_id, memory_table in memory_ids_with_tables:
        pid = pin_memory(conn, memory_id, memory_table, agent_id=agent_id, label=label)
        pin_ids.append(pid)
    return pin_ids


def batch_tag_memories(conn, memory_ids_with_tables, tag_id):
    """Apply a tag to multiple memories."""
    for memory_id, memory_table in memory_ids_with_tables:
        aid = _new_id()
        conn.execute(
            """INSERT INTO tag_assignments (id, tag_id, target_id, target_table)
               VALUES (?, ?, ?, ?)""",
            (aid, tag_id, memory_id, memory_table),
        )
    conn.commit()


def batch_delete_memories(conn, memory_ids_with_tables):
    """Delete multiple memories. STM entries are set to expired; MTM/LTM are deleted."""
    for memory_id, memory_table in memory_ids_with_tables:
        if memory_table == "short_term_memory":
            conn.execute(
                "UPDATE short_term_memory SET status = 'expired' WHERE id = ?",
                (memory_id,),
            )
        else:
            conn.execute(f"DELETE FROM {memory_table} WHERE id = ?", (memory_id,))
    conn.commit()


def batch_promote_memories(conn, memory_ids, from_tier):
    """Promote memories to the next tier. Returns list of new IDs."""
    # This is a simplified batch promote — real promotion uses the consolidation engine
    promoted = []
    for mid in memory_ids:
        if from_tier == "short":
            row = conn.execute("SELECT * FROM short_term_memory WHERE id = ?",
                               (mid,)).fetchone()
            if row:
                entry = dict(row)
                new_id = _new_id()
                conn.execute(
                    """INSERT INTO midterm_memory
                       (id, agent_id, content, embedding, confidence, source_ids, category)
                       VALUES (?, ?, ?, ?, 0.5, ?, 'observation')""",
                    (new_id, entry["agent_id"], entry["content"],
                     entry.get("embedding"), json.dumps([mid])),
                )
                conn.execute(
                    "UPDATE short_term_memory SET status = 'promoted' WHERE id = ?",
                    (mid,),
                )
                promoted.append(new_id)
        elif from_tier == "mid":
            row = conn.execute("SELECT * FROM midterm_memory WHERE id = ?",
                               (mid,)).fetchone()
            if row:
                entry = dict(row)
                new_id = _new_id()
                conn.execute(
                    """INSERT INTO long_term_memory
                       (id, agent_id, content, embedding, confidence, provenance, category)
                       VALUES (?, ?, ?, ?, ?, ?, 'fact')""",
                    (new_id, entry["agent_id"], entry["content"],
                     entry.get("embedding"), entry.get("confidence", 0.9),
                     json.dumps({"promoted_from": mid})),
                )
                conn.execute("DELETE FROM midterm_memory WHERE id = ?", (mid,))
                promoted.append(new_id)
    conn.commit()
    return promoted
