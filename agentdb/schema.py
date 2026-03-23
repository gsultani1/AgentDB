"""
SQLite schema definition for AgentDB v1.4.

Contains all 23 tables organized into five functional groups:
- Memory Tables (short_term_memory, midterm_memory, long_term_memory)
- Knowledge Infrastructure (agents, skills, skill_implementations, relations, entities, goals, tags, tag_assignments)
- Workspace Awareness (workspaces, workspace_files)
- Operational Support (sessions, meta_config, contradictions, audit_log, feedback, context_snapshots, notification_queue)
- Performance Optimization (views, embeddings_cache)

Also contains trigger definitions for polymorphic referential integrity,
cascade deletes, and FTS5 virtual tables for BM25 keyword search.
"""

# ── Memory Tables ──

CREATE_SHORT_TERM_MEMORY = """
CREATE TABLE IF NOT EXISTS short_term_memory (
    id              TEXT PRIMARY KEY,
    agent_id        TEXT NOT NULL DEFAULT 'default',
    timestamp       DATETIME NOT NULL DEFAULT (datetime('now')),
    source          TEXT NOT NULL CHECK(source IN (
                        'conversation', 'tool_output', 'sensor',
                        'chatgpt_import', 'claude_import',
                        'markdown_authored')),
    content         TEXT NOT NULL,
    embedding       BLOB,
    ttl_seconds     INTEGER NOT NULL DEFAULT 3600,
    session_id      TEXT REFERENCES sessions(id),
    status          TEXT NOT NULL DEFAULT 'active' CHECK(status IN (
                        'active', 'promoted', 'expired', 'imported'))
);
"""

CREATE_MIDTERM_MEMORY = """
CREATE TABLE IF NOT EXISTS midterm_memory (
    id              TEXT PRIMARY KEY,
    agent_id        TEXT NOT NULL DEFAULT 'default',
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    last_accessed   DATETIME NOT NULL DEFAULT (datetime('now')),
    content         TEXT NOT NULL,
    embedding       BLOB,
    confidence      REAL NOT NULL DEFAULT 0.5 CHECK(confidence >= 0.0 AND confidence <= 1.0),
    source_ids      JSON,
    entity_ids      JSON,
    decay_weight    REAL NOT NULL DEFAULT 1.0,
    category        TEXT NOT NULL DEFAULT 'observation' CHECK(category IN (
                        'observation', 'pattern', 'inference'))
);
"""

CREATE_LONG_TERM_MEMORY = """
CREATE TABLE IF NOT EXISTS long_term_memory (
    id              TEXT PRIMARY KEY,
    agent_id        TEXT NOT NULL DEFAULT 'default',
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    last_validated  DATETIME NOT NULL DEFAULT (datetime('now')),
    content         TEXT NOT NULL,
    embedding       BLOB,
    confidence      REAL NOT NULL DEFAULT 0.9 CHECK(confidence >= 0.0 AND confidence <= 1.0),
    provenance      JSON,
    entity_ids      JSON,
    category        TEXT NOT NULL DEFAULT 'fact' CHECK(category IN (
                        'fact', 'relationship', 'preference', 'procedure', 'identity',
                        'directive'))
);
"""

# ── Knowledge Infrastructure ──

CREATE_AGENTS = """
CREATE TABLE IF NOT EXISTS agents (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    last_active     DATETIME,
    config          JSON
);
"""

CREATE_SKILLS = """
CREATE TABLE IF NOT EXISTS skills (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL,
    embedding       BLOB,
    input_schema    JSON,
    output_schema   JSON,
    version         INTEGER NOT NULL DEFAULT 1,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    last_used       DATETIME,
    use_count       INTEGER NOT NULL DEFAULT 0,
    success_rate    REAL NOT NULL DEFAULT 0.0,
    execution_type  TEXT NOT NULL CHECK(execution_type IN (
                        'prompt_template', 'code_procedure',
                        'tool_invocation', 'composite'))
);
"""

CREATE_SKILL_IMPLEMENTATIONS = """
CREATE TABLE IF NOT EXISTS skill_implementations (
    id              TEXT PRIMARY KEY,
    skill_id        TEXT NOT NULL REFERENCES skills(id),
    version         INTEGER NOT NULL,
    language        TEXT NOT NULL CHECK(language IN (
                        'python', 'bash', 'prompt_template',
                        'javascript', 'composite')),
    code            TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    dependencies    JSON,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    is_active       BOOLEAN NOT NULL DEFAULT 0,
    execution_order INTEGER
);
"""

CREATE_RELATIONS = """
CREATE TABLE IF NOT EXISTS relations (
    id              TEXT PRIMARY KEY,
    source_id       TEXT NOT NULL,
    source_table    TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    target_table    TEXT NOT NULL,
    edge_type       TEXT NOT NULL CHECK(edge_type IN (
                        'derived_from', 'contradicts', 'reinforces',
                        'applied_to', 'related_to', 'imports',
                        'configures', 'tests', 'documents', 'chunk_of')),
    weight          REAL NOT NULL DEFAULT 1.0,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    context         TEXT
);
"""

CREATE_ENTITIES = """
CREATE TABLE IF NOT EXISTS entities (
    id              TEXT PRIMARY KEY,
    canonical_name  TEXT NOT NULL,
    entity_type     TEXT NOT NULL CHECK(entity_type IN (
                        'person', 'company', 'project',
                        'location', 'concept', 'document')),
    embedding       BLOB,
    first_seen      DATETIME NOT NULL DEFAULT (datetime('now')),
    last_seen       DATETIME NOT NULL DEFAULT (datetime('now')),
    aliases         JSON
);
"""

CREATE_GOALS = """
CREATE TABLE IF NOT EXISTS goals (
    id              TEXT PRIMARY KEY,
    description     TEXT NOT NULL,
    embedding       BLOB,
    priority        INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'active' CHECK(status IN (
                        'active', 'completed', 'paused', 'abandoned')),
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    deadline        DATETIME,
    parent_goal_id  TEXT REFERENCES goals(id),
    completed_at    DATETIME
);
"""

CREATE_TAGS = """
CREATE TABLE IF NOT EXISTS tags (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    color           TEXT
);
"""

CREATE_TAG_ASSIGNMENTS = """
CREATE TABLE IF NOT EXISTS tag_assignments (
    id              TEXT PRIMARY KEY,
    tag_id          TEXT NOT NULL REFERENCES tags(id),
    target_id       TEXT NOT NULL,
    target_table    TEXT NOT NULL
);
"""

# ── Workspace Awareness ──

CREATE_WORKSPACES = """
CREATE TABLE IF NOT EXISTS workspaces (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    root_path       TEXT NOT NULL,
    workspace_type  TEXT NOT NULL CHECK(workspace_type IN (
                        'codebase', 'project_folder', 'data_directory')),
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    last_scanned    DATETIME,
    metadata        JSON
);
"""

CREATE_WORKSPACE_FILES = """
CREATE TABLE IF NOT EXISTS workspace_files (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id),
    relative_path   TEXT NOT NULL,
    file_type       TEXT NOT NULL CHECK(file_type IN (
                        'python', 'config', 'markdown', 'image',
                        'binary', 'directory')),
    depth           INTEGER NOT NULL DEFAULT 0,
    size_bytes      INTEGER,
    file_last_modified DATETIME,
    last_scanned    DATETIME,
    content_hash    TEXT,
    embedding       BLOB,
    summary         TEXT
);
"""

# ── Operational Support ──

CREATE_SESSIONS = """
CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,
    started_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    ended_at        DATETIME,
    summary         TEXT,
    embedding       BLOB,
    status          TEXT NOT NULL DEFAULT 'active' CHECK(status IN (
                        'active', 'closed')),
    workspace_id    TEXT REFERENCES workspaces(id)
);
"""

CREATE_META_CONFIG = """
CREATE TABLE IF NOT EXISTS meta_config (
    id              TEXT PRIMARY KEY,
    key             TEXT NOT NULL UNIQUE,
    value           TEXT NOT NULL,
    updated_at      DATETIME NOT NULL DEFAULT (datetime('now'))
);
"""

CREATE_CONTRADICTIONS = """
CREATE TABLE IF NOT EXISTS contradictions (
    id              TEXT PRIMARY KEY,
    memory_a_id     TEXT NOT NULL,
    memory_a_table  TEXT NOT NULL,
    memory_b_id     TEXT NOT NULL,
    memory_b_table  TEXT NOT NULL,
    resolution      TEXT NOT NULL DEFAULT 'unresolved' CHECK(resolution IN (
                        'a_kept', 'b_kept', 'both_revised',
                        'merged', 'unresolved')),
    reasoning       TEXT,
    resolved_at     DATETIME,
    resolved_by     TEXT CHECK(resolved_by IN ('agent', 'user') OR resolved_by IS NULL)
);
"""

CREATE_AUDIT_LOG = """
CREATE TABLE IF NOT EXISTS audit_log (
    id              TEXT PRIMARY KEY,
    timestamp       DATETIME NOT NULL DEFAULT (datetime('now')),
    table_name      TEXT NOT NULL,
    row_id          TEXT NOT NULL,
    operation       TEXT NOT NULL CHECK(operation IN (
                        'insert', 'update', 'delete', 'promote', 'demote')),
    before_snapshot JSON,
    after_snapshot  JSON,
    triggered_by    TEXT NOT NULL CHECK(triggered_by IN (
                        'consolidation', 'user_feedback', 'agent_inference',
                        'migration', 'markdown_import', 'manual'))
);
"""

CREATE_FEEDBACK = """
CREATE TABLE IF NOT EXISTS feedback (
    id              TEXT PRIMARY KEY,
    target_id       TEXT NOT NULL,
    target_table    TEXT NOT NULL,
    feedback_type   TEXT NOT NULL CHECK(feedback_type IN (
                        'correction', 'endorsement', 'annotation',
                        'deletion_request')),
    content         TEXT NOT NULL,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    processed       BOOLEAN NOT NULL DEFAULT 0
);
"""

CREATE_CONTEXT_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS context_snapshots (
    id                  TEXT PRIMARY KEY,
    timestamp           DATETIME NOT NULL DEFAULT (datetime('now')),
    trigger_description TEXT NOT NULL,
    memory_ids          JSON,
    skill_ids           JSON,
    relation_ids        JSON,
    goal_id             TEXT REFERENCES goals(id),
    outcome             TEXT
);
"""

CREATE_NOTIFICATION_QUEUE = """
CREATE TABLE IF NOT EXISTS notification_queue (
    id              TEXT PRIMARY KEY,
    agent_id        TEXT NOT NULL DEFAULT 'default',
    trigger_type    TEXT NOT NULL CHECK(trigger_type IN (
                        'goal_match', 'alert_condition',
                        'contradiction_detected', 'consolidation_complete')),
    title           TEXT NOT NULL,
    body            TEXT,
    priority        TEXT NOT NULL DEFAULT 'medium' CHECK(priority IN (
                        'low', 'medium', 'high', 'critical')),
    related_ids     JSON,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    read            BOOLEAN NOT NULL DEFAULT 0,
    delivered       BOOLEAN NOT NULL DEFAULT 0
);
"""

# ── Performance Optimization ──

CREATE_VIEWS = """
CREATE TABLE IF NOT EXISTS views (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    center_node_id      TEXT NOT NULL,
    center_node_table   TEXT NOT NULL,
    depth_limit         INTEGER NOT NULL DEFAULT 2,
    filters             JSON,
    layout_hints        JSON
);
"""

CREATE_EMBEDDINGS_CACHE = """
CREATE TABLE IF NOT EXISTS embeddings_cache (
    id              TEXT PRIMARY KEY,
    node_a_id       TEXT NOT NULL,
    node_a_table    TEXT NOT NULL,
    node_b_id       TEXT NOT NULL,
    node_b_table    TEXT NOT NULL,
    similarity_score REAL NOT NULL,
    computed_at     DATETIME NOT NULL DEFAULT (datetime('now'))
);
"""

# ── Indexes ──

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_stm_session ON short_term_memory(session_id);",
    "CREATE INDEX IF NOT EXISTS idx_stm_status ON short_term_memory(status);",
    "CREATE INDEX IF NOT EXISTS idx_stm_timestamp ON short_term_memory(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_stm_source ON short_term_memory(source);",
    "CREATE INDEX IF NOT EXISTS idx_mtm_confidence ON midterm_memory(confidence);",
    "CREATE INDEX IF NOT EXISTS idx_mtm_category ON midterm_memory(category);",
    "CREATE INDEX IF NOT EXISTS idx_mtm_decay ON midterm_memory(decay_weight);",
    "CREATE INDEX IF NOT EXISTS idx_mtm_last_accessed ON midterm_memory(last_accessed);",
    "CREATE INDEX IF NOT EXISTS idx_ltm_confidence ON long_term_memory(confidence);",
    "CREATE INDEX IF NOT EXISTS idx_ltm_category ON long_term_memory(category);",
    "CREATE INDEX IF NOT EXISTS idx_ltm_last_validated ON long_term_memory(last_validated);",
    "CREATE INDEX IF NOT EXISTS idx_skills_exec_type ON skills(execution_type);",
    "CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name);",
    "CREATE INDEX IF NOT EXISTS idx_skill_impl_skill ON skill_implementations(skill_id);",
    "CREATE INDEX IF NOT EXISTS idx_skill_impl_active ON skill_implementations(is_active);",
    "CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_id, source_table);",
    "CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_id, target_table);",
    "CREATE INDEX IF NOT EXISTS idx_relations_edge ON relations(edge_type);",
    "CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(canonical_name);",
    "CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);",
    "CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status);",
    "CREATE INDEX IF NOT EXISTS idx_goals_priority ON goals(priority);",
    "CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);",
    "CREATE INDEX IF NOT EXISTS idx_tag_assign_tag ON tag_assignments(tag_id);",
    "CREATE INDEX IF NOT EXISTS idx_tag_assign_target ON tag_assignments(target_id, target_table);",
    "CREATE INDEX IF NOT EXISTS idx_ws_files_workspace ON workspace_files(workspace_id);",
    "CREATE INDEX IF NOT EXISTS idx_ws_files_path ON workspace_files(relative_path);",
    "CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);",
    "CREATE INDEX IF NOT EXISTS idx_config_key ON meta_config(key);",
    "CREATE INDEX IF NOT EXISTS idx_contradictions_resolution ON contradictions(resolution);",
    "CREATE INDEX IF NOT EXISTS idx_audit_table ON audit_log(table_name);",
    "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_audit_operation ON audit_log(operation);",
    "CREATE INDEX IF NOT EXISTS idx_feedback_target ON feedback(target_id, target_table);",
    "CREATE INDEX IF NOT EXISTS idx_feedback_processed ON feedback(processed);",
    "CREATE INDEX IF NOT EXISTS idx_context_snap_goal ON context_snapshots(goal_id);",
    "CREATE INDEX IF NOT EXISTS idx_context_snap_time ON context_snapshots(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_emb_cache_a ON embeddings_cache(node_a_id, node_a_table);",
    "CREATE INDEX IF NOT EXISTS idx_emb_cache_b ON embeddings_cache(node_b_id, node_b_table);",
    "CREATE INDEX IF NOT EXISTS idx_stm_agent ON short_term_memory(agent_id);",
    "CREATE INDEX IF NOT EXISTS idx_mtm_agent ON midterm_memory(agent_id);",
    "CREATE INDEX IF NOT EXISTS idx_ltm_agent ON long_term_memory(agent_id);",
    "CREATE INDEX IF NOT EXISTS idx_notif_agent ON notification_queue(agent_id);",
    "CREATE INDEX IF NOT EXISTS idx_notif_read ON notification_queue(read);",
    "CREATE INDEX IF NOT EXISTS idx_notif_priority ON notification_queue(priority);",
    "CREATE INDEX IF NOT EXISTS idx_agents_last_active ON agents(last_active);",
]

# ── All content tables that participate in polymorphic relations ──

CONTENT_TABLES = [
    "short_term_memory",
    "midterm_memory",
    "long_term_memory",
    "skills",
    "skill_implementations",
    "entities",
    "goals",
    "workspaces",
    "workspace_files",
    "sessions",
]

# ── All valid table names for polymorphic references ──

POLYMORPHIC_TABLES = CONTENT_TABLES + ["tags", "context_snapshots", "feedback"]

# ── Trigger Definitions ──

def _build_polymorphic_check_case(column_id, column_table):
    """Build a CASE expression that validates a polymorphic reference exists."""
    checks = []
    for table in CONTENT_TABLES:
        checks.append(
            f"WHEN NEW.{column_table} = '{table}' THEN "
            f"(SELECT COUNT(*) FROM {table} WHERE id = NEW.{column_id})"
        )
    return "CASE " + " ".join(checks) + " ELSE 0 END"


def _build_insert_validation_trigger(target_table, column_id, column_table, trigger_suffix=""):
    """Build a BEFORE INSERT trigger for polymorphic reference validation."""
    case_expr = _build_polymorphic_check_case(column_id, column_table)
    name = f"trg_{target_table}_validate_{column_id}{trigger_suffix}"
    return f"""
CREATE TRIGGER IF NOT EXISTS {name}
BEFORE INSERT ON {target_table}
FOR EACH ROW
WHEN (
    {case_expr}
) = 0
BEGIN
    SELECT RAISE(ABORT, '{target_table}: referenced {column_id} does not exist in {column_table}');
END;
"""


def _build_update_validation_trigger(target_table, column_id, column_table, trigger_suffix=""):
    """Build a BEFORE UPDATE trigger for polymorphic reference validation."""
    case_expr = _build_polymorphic_check_case(column_id, column_table)
    name = f"trg_{target_table}_validate_{column_id}_update{trigger_suffix}"
    return f"""
CREATE TRIGGER IF NOT EXISTS {name}
BEFORE UPDATE ON {target_table}
FOR EACH ROW
WHEN (
    {case_expr}
) = 0
BEGIN
    SELECT RAISE(ABORT, '{target_table}: referenced {column_id} does not exist in {column_table}');
END;
"""


# Relations table needs validation on both source and target
TRIGGER_RELATIONS_VALIDATE_SOURCE_INSERT = _build_insert_validation_trigger(
    "relations", "source_id", "source_table", "_src"
)
TRIGGER_RELATIONS_VALIDATE_TARGET_INSERT = _build_insert_validation_trigger(
    "relations", "target_id", "target_table", "_tgt"
)
TRIGGER_RELATIONS_VALIDATE_SOURCE_UPDATE = _build_update_validation_trigger(
    "relations", "source_id", "source_table", "_src"
)
TRIGGER_RELATIONS_VALIDATE_TARGET_UPDATE = _build_update_validation_trigger(
    "relations", "target_id", "target_table", "_tgt"
)

# tag_assignments validation
TRIGGER_TAG_ASSIGNMENTS_VALIDATE_INSERT = _build_insert_validation_trigger(
    "tag_assignments", "target_id", "target_table"
)
TRIGGER_TAG_ASSIGNMENTS_VALIDATE_UPDATE = _build_update_validation_trigger(
    "tag_assignments", "target_id", "target_table"
)

# feedback validation
TRIGGER_FEEDBACK_VALIDATE_INSERT = _build_insert_validation_trigger(
    "feedback", "target_id", "target_table"
)
TRIGGER_FEEDBACK_VALIDATE_UPDATE = _build_update_validation_trigger(
    "feedback", "target_id", "target_table"
)


def _build_cascade_delete_triggers(table):
    """Build AFTER DELETE triggers for a content table to clean up polymorphic references."""
    triggers = []

    # Clean relations where this table's row is source or target
    triggers.append(f"""
CREATE TRIGGER IF NOT EXISTS trg_{table}_cascade_relations
AFTER DELETE ON {table}
FOR EACH ROW
BEGIN
    DELETE FROM relations WHERE (source_id = OLD.id AND source_table = '{table}')
                             OR (target_id = OLD.id AND target_table = '{table}');
    DELETE FROM tag_assignments WHERE target_id = OLD.id AND target_table = '{table}';
    DELETE FROM feedback WHERE target_id = OLD.id AND target_table = '{table}';
END;
""")
    return triggers


# Build cascade triggers for all content tables
CASCADE_DELETE_TRIGGERS = []
for _t in CONTENT_TABLES:
    CASCADE_DELETE_TRIGGERS.extend(_build_cascade_delete_triggers(_t))

# Skills cascade also removes skill_implementations
TRIGGER_SKILLS_CASCADE_IMPLEMENTATIONS = """
CREATE TRIGGER IF NOT EXISTS trg_skills_cascade_implementations
AFTER DELETE ON skills
FOR EACH ROW
BEGIN
    DELETE FROM skill_implementations WHERE skill_id = OLD.id;
END;
"""

# Workspaces cascade removes workspace_files
TRIGGER_WORKSPACES_CASCADE_FILES = """
CREATE TRIGGER IF NOT EXISTS trg_workspaces_cascade_files
AFTER DELETE ON workspaces
FOR EACH ROW
BEGIN
    DELETE FROM workspace_files WHERE workspace_id = OLD.id;
END;
"""

# Tags cascade removes tag_assignments
TRIGGER_TAGS_CASCADE_ASSIGNMENTS = """
CREATE TRIGGER IF NOT EXISTS trg_tags_cascade_assignments
AFTER DELETE ON tags
FOR EACH ROW
BEGIN
    DELETE FROM tag_assignments WHERE tag_id = OLD.id;
END;
"""

# ── Ordered list of all CREATE TABLE statements ──

# ── FTS5 Virtual Tables for BM25 Keyword Search ──

CREATE_FTS_TABLES = [
    "CREATE VIRTUAL TABLE IF NOT EXISTS stm_fts USING fts5(content, content='short_term_memory', content_rowid='rowid');",
    "CREATE VIRTUAL TABLE IF NOT EXISTS mtm_fts USING fts5(content, content='midterm_memory', content_rowid='rowid');",
    "CREATE VIRTUAL TABLE IF NOT EXISTS ltm_fts USING fts5(content, content='long_term_memory', content_rowid='rowid');",
]

ALL_TABLES = [
    CREATE_AGENTS,            # agents first (referenced by agent_id columns)
    CREATE_SESSIONS,          # sessions before short_term_memory
    CREATE_SHORT_TERM_MEMORY,
    CREATE_MIDTERM_MEMORY,
    CREATE_LONG_TERM_MEMORY,
    CREATE_SKILLS,
    CREATE_SKILL_IMPLEMENTATIONS,
    CREATE_RELATIONS,
    CREATE_ENTITIES,
    CREATE_GOALS,
    CREATE_TAGS,
    CREATE_TAG_ASSIGNMENTS,
    CREATE_WORKSPACES,
    CREATE_WORKSPACE_FILES,
    CREATE_META_CONFIG,
    CREATE_CONTRADICTIONS,
    CREATE_AUDIT_LOG,
    CREATE_FEEDBACK,
    CREATE_CONTEXT_SNAPSHOTS,
    CREATE_NOTIFICATION_QUEUE,
    CREATE_VIEWS,
    CREATE_EMBEDDINGS_CACHE,
]

ALL_TRIGGERS = [
    TRIGGER_RELATIONS_VALIDATE_SOURCE_INSERT,
    TRIGGER_RELATIONS_VALIDATE_TARGET_INSERT,
    TRIGGER_RELATIONS_VALIDATE_SOURCE_UPDATE,
    TRIGGER_RELATIONS_VALIDATE_TARGET_UPDATE,
    TRIGGER_TAG_ASSIGNMENTS_VALIDATE_INSERT,
    TRIGGER_TAG_ASSIGNMENTS_VALIDATE_UPDATE,
    TRIGGER_FEEDBACK_VALIDATE_INSERT,
    TRIGGER_FEEDBACK_VALIDATE_UPDATE,
    TRIGGER_SKILLS_CASCADE_IMPLEMENTATIONS,
    TRIGGER_WORKSPACES_CASCADE_FILES,
    TRIGGER_TAGS_CASCADE_ASSIGNMENTS,
] + CASCADE_DELETE_TRIGGERS
