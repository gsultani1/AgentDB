"""
HTTP server for AgentDB.

Serves both the Operator API (/api/) and Agent API (/api/agent/)
on localhost. All responses use a consistent {status, data, error} envelope.

Uses Python's built-in http.server module — no framework dependencies.
"""

import json
import os
import re
import time
import traceback
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from agentdb.database import get_connection, verify_schema
from agentdb import crud
from agentdb.context import retrieve_context
from agentdb.embeddings import (
    generate_embedding,
    embedding_to_blob,
    blob_to_embedding,
    semantic_search,
)
from agentdb.middleware import (
    execute_chat_pipeline,
    get_identity_memories,
    get_llm_config,
)
from agentdb.markdown_parser import (
    process_markdown_document,
    reverse_generate_markdown,
    MarkdownFileWatcher,
)
from agentdb.scheduler import (
    ScheduledTaskRunner,
    compute_next_run,
    ensure_scheduler_schema,
    run_scheduled_task_now,
)


_db_path = None
_start_time = None
_static_dir = Path(__file__).parent / "static"
_allowed_origins = {"http://127.0.0.1", "http://localhost", "tauri://localhost"}
_last_import_result = None
_file_watcher = None
_task_scheduler = None


def _get_conn():
    """Get a fresh database connection for the current request."""
    return get_connection(_db_path)


def _check_agent_api_key(handler):
    """
    Validate the agent API key. Returns (authorized: bool, derived_agent_id: str | None).

    Lookup order:
    1. Per-agent key stored in agents.config as {"api_key": "..."} — if matched,
       derived_agent_id is set to that agent's id, overriding any body agent_id.
    2. Global agent_api_key in meta_config — matched key leaves agent_id body-provided.
    3. No key configured → open-by-default (True, None).
    """
    conn = _get_conn()
    try:
        provided_key = handler.headers.get("X-API-Key", "")

        # 1. Per-agent key lookup
        if provided_key:
            row = conn.execute(
                "SELECT id FROM agents WHERE json_extract(config, '$.api_key') = ?",
                (provided_key,),
            ).fetchone()
            if row:
                return True, row["id"]

        # 2. Global shared key
        configured = conn.execute(
            "SELECT value FROM meta_config WHERE key = 'agent_api_key'"
        ).fetchone()
        if configured is None or not configured[0]:
            return True, None
        return provided_key == configured[0], None
    finally:
        conn.close()


def _check_operator_auth(handler):
    """
    Validate operator access via Authorization: Bearer <key> or X-API-Key header.
    Returns True if authorized. Open-by-default when operator_api_key is empty.
    """
    conn = _get_conn()
    try:
        configured = conn.execute(
            "SELECT value FROM meta_config WHERE key = 'operator_api_key'"
        ).fetchone()
        if configured is None or not configured[0]:
            return True  # no key configured — open
        expected = configured[0]
        # Accept either Bearer token or X-API-Key
        auth_header = handler.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:] == expected
        return handler.headers.get("X-API-Key", "") == expected
    finally:
        conn.close()


def _json_response(handler, status_code, data=None, error=None):
    """Send a JSON response with the standard envelope."""
    body = {
        "status": "ok" if error is None else "error",
        "data": data,
        "error": error,
    }
    payload = json.dumps(body, default=str).encode("utf-8")
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(payload)))
    origin = handler.headers.get("Origin", "")
    if any(origin.startswith(o) for o in _allowed_origins) or not origin:
        handler.send_header("Access-Control-Allow-Origin", origin or "http://127.0.0.1")
    else:
        handler.send_header("Access-Control-Allow-Origin", "http://127.0.0.1")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key")
    handler.end_headers()
    handler.wfile.write(payload)


def _read_body(handler):
    """Read and parse the JSON request body."""
    length = int(handler.headers.get("Content-Length", 0))
    if length == 0:
        return {}
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8"))


def _match(pattern, path):
    """Match a URL pattern with {param} placeholders against a path."""
    regex = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", pattern)
    m = re.fullmatch(regex, path)
    if m:
        return m.groupdict()
    return None


class AgentDBHandler(BaseHTTPRequestHandler):
    """Request handler for all AgentDB API endpoints."""

    def log_message(self, format, *args):
        """Override to use simpler logging."""
        pass

    _MIME_TYPES = {
        '.html': 'text/html; charset=utf-8',
        '.css': 'text/css; charset=utf-8',
        '.js': 'application/javascript; charset=utf-8',
        '.json': 'application/json',
        '.svg': 'image/svg+xml',
        '.png': 'image/png',
        '.ico': 'image/x-icon',
        '.woff2': 'font/woff2',
        '.woff': 'font/woff',
        '.ttf': 'font/ttf',
    }

    def _serve_static(self, relative_path):
        """Serve a static file from the static directory with proper MIME types."""
        filepath = (_static_dir / relative_path).resolve()
        static_root = _static_dir.resolve()
        if not str(filepath).startswith(str(static_root)):
            self.send_response(403)
            self.end_headers()
            return
        if not filepath.is_file():
            return self._serve_static("index.html") if relative_path != "index.html" else None
        content = filepath.read_bytes()
        ext = filepath.suffix.lower()
        ct = self._MIME_TYPES.get(ext, 'application/octet-stream')
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache" if ext == '.html' else "public, max-age=3600")
        self.end_headers()
        self.wfile.write(content)

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        origin = self.headers.get("Origin", "")
        self.send_response(204)
        if any(origin.startswith(o) for o in _allowed_origins) or not origin:
            self.send_header("Access-Control-Allow-Origin", origin or "http://127.0.0.1")
        else:
            self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key")
        self.end_headers()

    def _require_agent_auth(self):
        """Check API key for agent endpoints. Returns False and sends 401 if unauthorized.
        Sets self._derived_agent_id to the agent bound to the presented key, or None."""
        authorized, derived = _check_agent_api_key(self)
        if not authorized:
            _json_response(self, 401, error="Invalid or missing API key. Set X-API-Key header.")
            return False
        self._derived_agent_id = derived
        return True

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        query_params = parse_qs(parsed.query)

        # Serve static UI
        if path in ("", "/", "/index.html"):
            return self._serve_static("index.html")

        # Serve static assets (css, js, images)
        if not path.startswith("/api/"):
            return self._serve_static(path.lstrip("/"))

        try:
            self._route_get(path, query_params)
        except Exception as e:
            traceback.print_exc()
            _json_response(self, 500, error=str(e))

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        try:
            body = _read_body(self)
            self._route_post(path, body)
        except Exception as e:
            _json_response(self, 500, error=str(e))

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        try:
            body = _read_body(self)
            self._route_put(path, body)
        except Exception as e:
            _json_response(self, 500, error=str(e))

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        try:
            self._route_delete(path)
        except Exception as e:
            traceback.print_exc()
            _json_response(self, 500, error=str(e))

    def _route_delete(self, path):
        if path.startswith("/api/"):
            if not _check_operator_auth(self):
                return _json_response(self, 401, error="Operator authentication required. Set Authorization: Bearer <key>.")
        conn = _get_conn()
        try:
            m = _match("/api/memories/short/{id}", path)
            if m:
                crud.delete_short_term_memory(conn, m["id"])
                return _json_response(self, 200, data={"deleted": m["id"]})
            m = _match("/api/memories/mid/{id}", path)
            if m:
                crud.delete_midterm_memory(conn, m["id"])
                return _json_response(self, 200, data={"deleted": m["id"]})
            m = _match("/api/memories/long/{id}", path)
            if m:
                crud.delete_long_term_memory(conn, m["id"])
                return _json_response(self, 200, data={"deleted": m["id"]})
            m = _match("/api/skills/{id}", path)
            if m:
                crud.delete_skill(conn, m["id"])
                return _json_response(self, 200, data={"deleted": m["id"]})
            m = _match("/api/entities/{id}", path)
            if m:
                crud.delete_entity(conn, m["id"])
                return _json_response(self, 200, data={"deleted": m["id"]})
            m = _match("/api/goals/{id}", path)
            if m:
                crud.delete_goal(conn, m["id"])
                return _json_response(self, 200, data={"deleted": m["id"]})
            m = _match("/api/feedback/{id}", path)
            if m:
                crud.delete_feedback(conn, m["id"])
                return _json_response(self, 200, data={"deleted": m["id"]})
            m = _match("/api/scheduled-tasks/{id}", path)
            if m:
                crud.delete_scheduled_task(conn, m["id"])
                return _json_response(self, 200, data={"deleted": m["id"]})
            _json_response(self, 404, error=f"Not found: {path}")
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════════════
    # GET ROUTING
    # ══════════════════════════════════════════════════════════════

    def _route_get(self, path, qp):
        # Operator auth on all /api/* routes (health exempt for monitoring)
        if path.startswith("/api/") and path not in ("/api/agent/health",):
            if not _check_operator_auth(self):
                return _json_response(self, 401, error="Operator authentication required. Set Authorization: Bearer <key>.")

        # Enforce API key on agent routes (health is exempt for monitoring)
        if path.startswith("/api/agent/") and path != "/api/agent/health":
            if not self._require_agent_auth():
                return

        conn = _get_conn()
        try:
            # ── Agent API ──
            if path == "/api/agent/health":
                return self._agent_health(conn)
            if path == "/api/agent/identity":
                return self._agent_identity(conn)

            # ── Operator API ──
            if path == "/api/stats":
                return self._op_stats(conn)
            if path == "/api/config":
                return self._op_config_list(conn)
            if path == "/api/entities":
                return self._op_entities_list(conn, qp)
            if path == "/api/skills":
                return self._op_skills_list(conn, qp)
            if path == "/api/goals":
                return self._op_goals_list(conn, qp)
            if path == "/api/contradictions":
                return self._op_contradictions_list(conn, qp)
            if path == "/api/audit":
                return self._op_audit_list(conn, qp)
            if path == "/api/views":
                return self._op_views_list(conn)
            if path == "/api/workspaces":
                return self._op_workspaces_list(conn)
            if path == "/api/agents":
                return self._op_agents_list(conn)
            if path == "/api/notifications":
                return self._op_notifications_list(conn, qp)
            if path == "/api/scheduled-tasks":
                return self._op_scheduled_tasks_list(conn, qp)
            if path == "/api/scheduler/status":
                return self._op_scheduler_status(conn)
            if path == "/api/mcp/status":
                return _json_response(self, 200, data={
                    "enabled": crud.get_config_value(conn, "mcp_enabled", "false") == "true",
                    "transport": crud.get_config_value(conn, "mcp_transport", "stdio"),
                    "port": int(crud.get_config_value(conn, "mcp_port", "8421")),
                })
            if path == "/api/import/status":
                if _last_import_result:
                    return _json_response(self, 200, data=_last_import_result)
                return _json_response(self, 200, data={"status": "idle"})
            if path == "/api/markdown/watcher/status":
                return self._op_watcher_status(conn)
            if path == "/api/encryption/status":
                from agentdb.database import encryption_status
                return _json_response(self, 200, data=encryption_status())

            # Parameterized routes
            m = _match("/api/memories/{tier}", path)
            if m:
                return self._op_memories_list(conn, m["tier"], qp)
            m = _match("/api/memories/{tier}/{id}", path)
            if m:
                return self._op_memory_detail(conn, m["tier"], m["id"])
            m = _match("/api/entities/{id}/graph", path)
            if m:
                return self._op_entity_graph(conn, m["id"], qp)
            m = _match("/api/skills/{id}/implementations", path)
            if m:
                return self._op_skill_implementations(conn, m["id"])
            m = _match("/api/relations/{node_id}", path)
            if m:
                return self._op_relations(conn, m["node_id"])
            m = _match("/api/config/{key}", path)
            if m:
                return self._op_config_get(conn, m["key"])
            m = _match("/api/markdown/reverse/{table}/{id}", path)
            if m:
                return self._op_markdown_reverse(conn, m["table"], m["id"])
            m = _match("/api/workspaces/{id}/files", path)
            if m:
                files = crud.list_workspace_files(conn, m["id"])
                for f in files:
                    f.pop("embedding", None)
                return _json_response(self, 200, data=files)
            m = _match("/api/agents/{id}", path)
            if m:
                agent = crud.get_agent(conn, m["id"])
                if agent:
                    return _json_response(self, 200, data=agent)
                return _json_response(self, 404, error="Agent not found")
            m = _match("/api/scheduled-tasks/{id}", path)
            if m:
                return self._op_scheduled_task_detail(conn, m["id"])

            _json_response(self, 404, error=f"Not found: {path}")
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════════════
    # POST ROUTING
    # ══════════════════════════════════════════════════════════════

    def _route_post(self, path, body):
        # Operator auth on all /api/* routes
        if path.startswith("/api/"):
            if not _check_operator_auth(self):
                return _json_response(self, 401, error="Operator authentication required. Set Authorization: Bearer <key>.")

        # Enforce API key on agent routes
        if path.startswith("/api/agent/"):
            if not self._require_agent_auth():
                return

        conn = _get_conn()
        try:
            # ── Agent API ──
            if path == "/api/agent/context":
                return self._agent_context(conn, body)
            if path == "/api/agent/ingest":
                return self._agent_ingest(conn, body)
            if path == "/api/agent/ingest/batch":
                return self._agent_ingest_batch(conn, body)
            if path == "/api/agent/skill/match":
                return self._agent_skill_match(conn, body)
            if path == "/api/agent/skill/execute":
                return self._agent_skill_execute(conn, body)
            if path == "/api/agent/goals/check":
                return self._agent_goals_check(conn, body)
            if path == "/api/agent/session/start":
                return self._agent_session_start(conn, body)
            if path == "/api/agent/session/end":
                return self._agent_session_end(conn, body)
            if path == "/api/agent/chat":
                return self._agent_chat(conn, body)

            # ── Operator API ──
            if path == "/api/memories/search":
                return self._op_memories_search(conn, body)
            if path == "/api/memories/short":
                return self._op_memory_create(conn, "short", body)
            if path == "/api/memories/mid":
                return self._op_memory_create(conn, "mid", body)
            if path == "/api/memories/long":
                return self._op_memory_create(conn, "long", body)
            if path == "/api/skills":
                return self._op_skill_create(conn, body)
            if path == "/api/entities":
                return self._op_entity_create(conn, body)
            if path == "/api/feedback":
                return self._op_feedback_submit(conn, body)
            if path == "/api/goals":
                return self._op_goal_create(conn, body)
            if path == "/api/views":
                return self._op_view_create(conn, body)
            if path == "/api/agents":
                return self._op_agent_create(conn, body)
            if path == "/api/notifications/dismiss":
                crud.dismiss_read_notifications(conn)
                return _json_response(self, 200, data={"message": "Read notifications dismissed"})
            if path == "/api/scheduled-tasks":
                return self._op_scheduled_task_create(conn, body)
            if path == "/api/maintenance/consolidate":
                from agentdb.consolidation import run_consolidation_cycle
                result = run_consolidation_cycle(conn)
                return _json_response(self, 200, data=result)
            if path == "/api/maintenance/sleep-cycle":
                from agentdb.sleep import run_sleep_cycle
                result = run_sleep_cycle(conn)
                return _json_response(self, 200, data=result)
            if path == "/api/maintenance/integrity-check":
                result = _run_integrity_check(conn)
                return _json_response(self, 200, data=result)
            if path == "/api/workspaces/scan":
                # Scan all registered workspaces
                from agentdb.workspace_scanner import scan_workspace
                workspaces = crud.list_workspaces(conn)
                results = []
                for ws in workspaces:
                    results.append(scan_workspace(conn, ws["id"]))
                return _json_response(self, 200, data={"workspaces": results})
            if path == "/api/encryption/rekey":
                from agentdb.database import rekey_database
                old_pass = body.get("old_passphrase")
                new_pass = body.get("new_passphrase")
                try:
                    rekey_database(_db_path, old_pass, new_pass)
                    return _json_response(self, 200, data={"rekeyed": True})
                except RuntimeError as e:
                    return _json_response(self, 400, error=str(e))
            if path == "/api/markdown/submit":
                return self._op_markdown_submit(conn, body)
            if path == "/api/markdown/batch":
                return self._op_markdown_batch(conn, body)
            if path == "/api/import":
                global _last_import_result
                file_path = body.get("file_path", "")
                provider = body.get("provider", "chatgpt")
                if not file_path:
                    return _json_response(self, 400, error="file_path is required")
                if not os.path.isfile(file_path):
                    return _json_response(self, 400, error=f"File not found: {file_path}")
                from agentdb.migration import run_migration_pipeline
                result = run_migration_pipeline(conn, file_path, provider)
                _last_import_result = {**result, "status": "completed"}
                return _json_response(self, 200, data=_last_import_result)

            m = _match("/api/agents/{id}/rotate-key", path)
            if m:
                return self._op_agent_rotate_key(conn, m["id"])
            m = _match("/api/workspaces/{id}/scan", path)
            if m:
                from agentdb.workspace_scanner import scan_workspace
                result = scan_workspace(conn, m["id"])
                return _json_response(self, 200, data=result)
            m = _match("/api/contradictions/{id}/resolve", path)
            if m:
                return self._op_contradiction_resolve(conn, m["id"], body)
            m = _match("/api/skills/{id}/rollback/{version}", path)
            if m:
                return self._op_skill_rollback(conn, m["id"], int(m["version"]))
            m = _match("/api/scheduled-tasks/{id}/run", path)
            if m:
                result = run_scheduled_task_now(conn, m["id"])
                return _json_response(self, 200, data=result)

            _json_response(self, 404, error=f"Not found: {path}")
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════════════
    # PUT ROUTING
    # ══════════════════════════════════════════════════════════════

    def _route_put(self, path, body):
        if path.startswith("/api/"):
            if not _check_operator_auth(self):
                return _json_response(self, 401, error="Operator authentication required. Set Authorization: Bearer <key>.")
        conn = _get_conn()
        try:
            m = _match("/api/config/{key}", path)
            if m:
                return self._op_config_set(conn, m["key"], body)
            m = _match("/api/skills/{id}", path)
            if m:
                return self._op_skill_update(conn, m["id"], body)
            m = _match("/api/notifications/{id}/read", path)
            if m:
                crud.mark_notification_read(conn, m["id"])
                return _json_response(self, 200, data={"id": m["id"], "read": True})
            m = _match("/api/agents/{id}", path)
            if m:
                result = crud.update_agent(conn, m["id"], **body)
                return _json_response(self, 200, data={"id": m["id"], "updated": result})
            m = _match("/api/memories/short/{id}", path)
            if m:
                crud.update_short_term_memory(conn, m["id"], **body)
                return _json_response(self, 200, data={"id": m["id"], "updated": True})
            m = _match("/api/memories/mid/{id}", path)
            if m:
                crud.update_midterm_memory(conn, m["id"], **body)
                return _json_response(self, 200, data={"id": m["id"], "updated": True})
            m = _match("/api/memories/long/{id}", path)
            if m:
                crud.update_long_term_memory(conn, m["id"], **body)
                return _json_response(self, 200, data={"id": m["id"], "updated": True})
            m = _match("/api/goals/{id}", path)
            if m:
                crud.update_goal(conn, m["id"], **body)
                return _json_response(self, 200, data={"id": m["id"], "updated": True})
            m = _match("/api/entities/{id}", path)
            if m:
                crud.update_entity(conn, m["id"], **body)
                return _json_response(self, 200, data={"id": m["id"], "updated": True})
            m = _match("/api/scheduled-tasks/{id}", path)
            if m:
                return self._op_scheduled_task_update(conn, m["id"], body)

            _json_response(self, 404, error=f"Not found: {path}")
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════════════
    # AGENT API HANDLERS
    # ══════════════════════════════════════════════════════════════

    def _agent_health(self, conn):
        schema = verify_schema(conn)
        uptime = round(time.time() - _start_time, 1) if _start_time else 0
        last_consol = crud.get_config_value(conn, "last_consolidation_timestamp", "never")
        _json_response(self, 200, data={
            "database_ok": schema["ok"],
            "sidecar_uptime_seconds": uptime,
            "embedding_model": crud.get_config_value(conn, "embedding_model"),
            "last_consolidation": last_consol,
        })

    def _agent_identity(self, conn):
        memories = get_identity_memories(conn)
        _json_response(self, 200, data=memories)

    def _agent_context(self, conn, body):
        query = body.get("query", "")
        if not query:
            return _json_response(self, 400, error="'query' is required")
        filters = body.get("filters", {})
        agent_id = getattr(self, "_derived_agent_id", None) or body.get("agent_id")
        include_agents = body.get("include_agents")  # list[str] | None
        if include_agents is not None and not isinstance(include_agents, list):
            return _json_response(self, 400, error="'include_agents' must be a list of agent ID strings")
        payload = retrieve_context(conn, query, filters=filters, agent_id=agent_id,
                                   include_agents=include_agents)
        _json_response(self, 200, data=payload)

    def _agent_ingest(self, conn, body):
        content = body.get("content", "")
        if not content:
            return _json_response(self, 400, error="'content' is required")
        source = body.get("source", "conversation")
        session_id = body.get("session_id")
        agent_id = getattr(self, "_derived_agent_id", None) or body.get("agent_id", "default")
        embedding = embedding_to_blob(generate_embedding(content))
        mid = crud.create_short_term_memory(
            conn, content, source, embedding=embedding, session_id=session_id,
            agent_id=agent_id,
        )
        _json_response(self, 201, data={"id": mid})

    def _agent_ingest_batch(self, conn, body):
        observations = body.get("observations", [])
        if not observations:
            return _json_response(self, 400, error="'observations' array is required")
        batch_agent_id = getattr(self, "_derived_agent_id", None) or body.get("agent_id", "default")
        ids = []
        for obs in observations:
            content = obs.get("content", "")
            if not content:
                continue
            source = obs.get("source", "conversation")
            session_id = obs.get("session_id")
            agent_id = obs.get("agent_id", batch_agent_id)
            embedding = embedding_to_blob(generate_embedding(content))
            mid = crud.create_short_term_memory(
                conn, content, source, embedding=embedding, session_id=session_id,
                agent_id=agent_id,
            )
            ids.append(mid)
        _json_response(self, 201, data={"ids": ids})

    def _agent_skill_match(self, conn, body):
        description = body.get("description", "")
        if not description:
            return _json_response(self, 400, error="'description' is required")
        query_emb = generate_embedding(description)
        rows = conn.execute(
            "SELECT id, embedding FROM skills WHERE embedding IS NOT NULL"
        ).fetchall()
        candidates = [(r["id"], r["embedding"]) for r in rows]
        threshold = float(crud.get_config_value(conn, "skill_similarity_threshold", "0.6"))
        results = semantic_search(query_emb, candidates, top_k=10)
        skills = []
        for sid, score in results:
            if score < threshold:
                continue
            skill = crud.get_skill(conn, sid)
            if skill:
                skill["similarity_score"] = round(score, 4)
                skill.pop("embedding", None)
                impls = crud.list_skill_implementations(conn, sid, active_only=True)
                if impls:
                    skill["active_implementation"] = {
                        "language": impls[0]["language"],
                        "dependencies": impls[0]["dependencies"],
                        "version": impls[0]["version"],
                    }
                skills.append(skill)
        _json_response(self, 200, data=skills)

    def _agent_skill_execute(self, conn, body):
        skill_id = body.get("skill_id", "")
        if not skill_id:
            return _json_response(self, 400, error="'skill_id' is required")
        inputs = body.get("inputs", {})
        skill = crud.get_skill(conn, skill_id)
        if not skill:
            return _json_response(self, 404, error="Skill not found")
        impls = crud.list_skill_implementations(conn, skill_id, active_only=True)
        if not impls:
            return _json_response(self, 404, error="No active implementation")
        impl = dict(impls[0])
        crud.update_skill(conn, skill_id,
                          use_count=skill["use_count"] + 1,
                          last_used=datetime.utcnow().isoformat())

        # Execute prompt_template skills by substituting inputs into the template
        if impl.get("language") == "prompt_template":
            template = impl.get("code", "")
            rendered = template
            for key, value in inputs.items():
                rendered = rendered.replace("{{" + key + "}}", str(value))
                rendered = rendered.replace("{" + key + "}", str(value))
            _json_response(self, 200, data={
                "skill_id": skill_id,
                "execution_type": "prompt_template",
                "rendered": rendered,
                "inputs": inputs,
            })
        else:
            # code_procedure, tool_invocation, composite — return implementation for caller to run
            _json_response(self, 200, data={
                "skill_id": skill_id,
                "execution_type": impl.get("language"),
                "implementation": impl,
                "inputs": inputs,
                "message": f"Return implementation to caller for {impl.get('language')} execution.",
            })

    def _agent_goals_check(self, conn, body):
        context = body.get("context", "")
        if not context:
            return _json_response(self, 400, error="'context' is required")
        query_emb = generate_embedding(context)
        rows = conn.execute(
            "SELECT id, embedding FROM goals WHERE status = 'active' AND embedding IS NOT NULL"
        ).fetchall()
        candidates = [(r["id"], r["embedding"]) for r in rows]
        threshold = float(crud.get_config_value(conn, "goal_similarity_threshold", "0.7"))
        results = semantic_search(query_emb, candidates, top_k=5)
        goals = []
        for gid, score in results:
            if score < threshold:
                continue
            goal = crud.get_goal(conn, gid)
            if goal:
                goal["similarity_score"] = round(score, 4)
                goal.pop("embedding", None)
                goals.append(goal)
        _json_response(self, 200, data=goals)

    def _agent_session_start(self, conn, body):
        workspace_id = body.get("workspace_id")
        sid = crud.create_session(conn, workspace_id=workspace_id)
        _json_response(self, 201, data={"session_id": sid})

    def _agent_session_end(self, conn, body):
        session_id = body.get("session_id", "")
        if not session_id:
            return _json_response(self, 400, error="'session_id' is required")
        summary = body.get("summary")
        embedding = None
        if summary:
            embedding = embedding_to_blob(generate_embedding(summary))
        crud.end_session(conn, session_id, summary=summary, embedding=embedding)
        _json_response(self, 200, data={"session_id": session_id, "status": "closed"})

    def _agent_chat(self, conn, body):
        message = body.get("message", "")
        if not message:
            return _json_response(self, 400, error="'message' is required")
        session_id = body.get("session_id", "")
        if not session_id:
            return _json_response(self, 400, error="'session_id' is required")
        history = body.get("history", [])
        agent_id = getattr(self, "_derived_agent_id", None) or body.get("agent_id")
        result = execute_chat_pipeline(conn, message, session_id, messages_history=history, agent_id=agent_id)
        _json_response(self, 200, data=result)

    # ══════════════════════════════════════════════════════════════
    # OPERATOR API HANDLERS
    # ══════════════════════════════════════════════════════════════

    def _op_stats(self, conn):
        tables = [
            ("short_term_memory", "short_term_memories"),
            ("midterm_memory", "midterm_memories"),
            ("long_term_memory", "long_term_memories"),
            ("skills", "skills"),
            ("skill_implementations", "skill_implementations"),
            ("entities", "entities"),
            ("goals", "goals"),
            ("relations", "relations"),
            ("tags", "tags"),
            ("sessions", "sessions"),
            ("contradictions", "contradictions"),
            ("feedback", "feedback"),
            ("audit_log", "audit_log_entries"),
            ("context_snapshots", "context_snapshots"),
            ("workspaces", "workspaces"),
            ("workspace_files", "workspace_files"),
            ("views", "views"),
            ("embeddings_cache", "embeddings_cache"),
            ("scheduled_tasks", "scheduled_tasks"),
        ]
        stats = {}
        for table, key in tables:
            stats[key] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        stats["unresolved_contradictions"] = conn.execute(
            "SELECT COUNT(*) FROM contradictions WHERE resolution = 'unresolved'"
        ).fetchone()[0]
        stats["pending_feedback"] = conn.execute(
            "SELECT COUNT(*) FROM feedback WHERE processed = 0"
        ).fetchone()[0]
        stats["active_goals"] = conn.execute(
            "SELECT COUNT(*) FROM goals WHERE status = 'active'"
        ).fetchone()[0]
        stats["llm_provider"] = crud.get_config_value(conn, "llm_provider", "")
        stats["embedding_model"] = crud.get_config_value(conn, "embedding_model", "")
        stats["markdown_watch_enabled"] = crud.get_config_value(conn, "markdown_watch_enabled", "false")
        stats["agents"] = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        stats["unread_notifications"] = crud.count_unread_notifications(conn)
        _json_response(self, 200, data=stats)

    def _op_config_list(self, conn):
        configs = crud.list_config(conn)
        # Mask sensitive keys
        for c in configs:
            if c["key"] in ("llm_api_key", "agent_api_key") and c["value"]:
                c["value"] = c["value"][:4] + "****" if len(c["value"]) > 4 else "****"
        _json_response(self, 200, data=configs)

    def _op_config_get(self, conn, key):
        cfg = crud.get_config(conn, key)
        if cfg is None:
            return _json_response(self, 404, error=f"Config key '{key}' not found")
        _json_response(self, 200, data=cfg)

    def _op_config_set(self, conn, key, body):
        value = body.get("value", "")
        crud.set_config(conn, key, str(value))
        _json_response(self, 200, data={"key": key, "value": str(value)})

    def _op_memories_list(self, conn, tier, qp):
        table_map = {
            "short": "short_term_memory",
            "mid": "midterm_memory",
            "long": "long_term_memory",
        }
        table = table_map.get(tier)
        if not table:
            return _json_response(self, 400, error=f"Invalid tier: {tier}")
        limit = int(qp.get("limit", [100])[0])
        offset = int(qp.get("offset", [0])[0])
        rows = conn.execute(
            f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        result = []
        for r in rows:
            entry = dict(r)
            entry.pop("embedding", None)
            result.append(entry)
        _json_response(self, 200, data=result)

    def _op_memory_detail(self, conn, tier, mid):
        table_map = {
            "short": "short_term_memory",
            "mid": "midterm_memory",
            "long": "long_term_memory",
        }
        table = table_map.get(tier)
        if not table:
            return _json_response(self, 400, error=f"Invalid tier: {tier}")
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (mid,)).fetchone()
        if not row:
            return _json_response(self, 404, error="Memory not found")
        entry = dict(row)
        entry.pop("embedding", None)
        entry["relations"] = crud.list_relations_for_node(conn, mid)
        entry["tags"] = crud.list_tag_assignments_for_target(conn, mid, table)
        entry["feedback"] = crud.list_feedback(conn, target_id=mid, target_table=table)
        _json_response(self, 200, data=entry)

    def _op_memories_search(self, conn, body):
        query = body.get("query", "")
        if not query:
            return _json_response(self, 400, error="'query' is required")
        tiers = body.get("tiers", ["short", "mid", "long"])
        limit = body.get("limit", 10)
        query_emb = generate_embedding(query)
        results = {}
        table_map = {
            "short": "short_term_memory",
            "mid": "midterm_memory",
            "long": "long_term_memory",
        }
        for tier in tiers:
            table = table_map.get(tier)
            if not table:
                continue
            rows = conn.execute(
                f"SELECT id, embedding FROM {table} WHERE embedding IS NOT NULL"
            ).fetchall()
            candidates = [(r["id"], r["embedding"]) for r in rows]
            ranked = semantic_search(query_emb, candidates, top_k=limit)
            tier_results = []
            for mid, score in ranked:
                row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (mid,)).fetchone()
                if row:
                    entry = dict(row)
                    entry.pop("embedding", None)
                    entry["similarity_score"] = round(score, 4)
                    tier_results.append(entry)
            results[tier] = tier_results
        _json_response(self, 200, data=results)

    def _op_entities_list(self, conn, qp):
        entity_type = qp.get("type", [None])[0]
        limit = int(qp.get("limit", [100])[0])
        entities = crud.list_entities(conn, entity_type=entity_type, limit=limit)
        for e in entities:
            e.pop("embedding", None)
        _json_response(self, 200, data=entities)

    def _op_entity_graph(self, conn, eid, qp):
        depth = int(qp.get("depth", [2])[0])
        entity = crud.get_entity(conn, eid)
        if not entity:
            return _json_response(self, 404, error="Entity not found")
        entity.pop("embedding", None)
        # BFS traversal
        visited = set()
        nodes = [{"id": eid, "table": "entities", "data": entity, "depth": 0}]
        edges = []
        queue = [(eid, "entities", 0)]
        visited.add((eid, "entities"))
        while queue:
            nid, ntable, d = queue.pop(0)
            if d >= depth:
                continue
            rels = crud.list_relations_for_node(conn, nid, ntable)
            for rel in rels:
                for side in [("source_id", "source_table"), ("target_id", "target_table")]:
                    other_id = rel[side[0]]
                    other_table = rel[side[1]]
                    if (other_id, other_table) == (nid, ntable):
                        continue
                    edges.append(rel)
                    if (other_id, other_table) not in visited:
                        visited.add((other_id, other_table))
                        # Fetch node data
                        node_row = conn.execute(
                            f"SELECT * FROM {other_table} WHERE id = ?", (other_id,)
                        ).fetchone()
                        node_data = dict(node_row) if node_row else {}
                        node_data.pop("embedding", None)
                        nodes.append({
                            "id": other_id,
                            "table": other_table,
                            "data": node_data,
                            "depth": d + 1,
                        })
                        queue.append((other_id, other_table, d + 1))
        _json_response(self, 200, data={"nodes": nodes, "edges": edges})

    def _op_skills_list(self, conn, qp):
        exec_type = qp.get("execution_type", [None])[0]
        skills = crud.list_skills(conn, execution_type=exec_type)
        for s in skills:
            s.pop("embedding", None)
        _json_response(self, 200, data=skills)

    def _op_skill_implementations(self, conn, sid):
        impls = crud.list_skill_implementations(conn, sid)
        _json_response(self, 200, data=impls)

    def _op_skill_update(self, conn, sid, body):
        result = crud.update_skill(conn, sid, **body)
        if not result:
            return _json_response(self, 400, error="No valid fields to update")
        _json_response(self, 200, data={"id": sid, "updated": True})

    def _op_skill_rollback(self, conn, sid, version):
        impls = crud.list_skill_implementations(conn, sid)
        target = None
        for impl in impls:
            if impl["version"] == version:
                target = impl
                break
        if not target:
            return _json_response(self, 404, error=f"Version {version} not found")
        crud.activate_skill_implementation(conn, target["id"], sid)
        crud.update_skill(conn, sid, version=version)
        _json_response(self, 200, data={"skill_id": sid, "rolled_back_to": version})

    def _op_goals_list(self, conn, qp):
        status = qp.get("status", [None])[0]
        goals = crud.list_goals(conn, status=status)
        for g in goals:
            g.pop("embedding", None)
        _json_response(self, 200, data=goals)

    def _op_goal_create(self, conn, body):
        description = body.get("description", "")
        if not description:
            return _json_response(self, 400, error="'description' is required")
        embedding = embedding_to_blob(generate_embedding(description))
        priority = body.get("priority", 0)
        deadline = body.get("deadline")
        parent_goal_id = body.get("parent_goal_id")
        gid = crud.create_goal(
            conn, description, embedding=embedding, priority=priority,
            deadline=deadline, parent_goal_id=parent_goal_id,
        )
        _json_response(self, 201, data={"id": gid})

    def _op_relations(self, conn, node_id):
        relations = crud.list_relations_for_node(conn, node_id)
        _json_response(self, 200, data=relations)

    def _op_contradictions_list(self, conn, qp):
        resolution = qp.get("resolution", [None])[0]
        contradictions = crud.list_contradictions(conn, resolution=resolution)
        _json_response(self, 200, data=contradictions)

    def _op_contradiction_resolve(self, conn, cid, body):
        resolution = body.get("resolution", "")
        reasoning = body.get("reasoning", "")
        resolved_by = body.get("resolved_by", "user")
        if not resolution:
            return _json_response(self, 400, error="'resolution' is required")
        crud.resolve_contradiction(conn, cid, resolution, reasoning, resolved_by)
        _json_response(self, 200, data={"id": cid, "resolved": True})

    def _op_audit_list(self, conn, qp):
        table_name = qp.get("table_name", [None])[0]
        operation = qp.get("operation", [None])[0]
        triggered_by = qp.get("triggered_by", [None])[0]
        limit = int(qp.get("limit", [100])[0])
        offset = int(qp.get("offset", [0])[0])
        entries = crud.list_audit_entries(
            conn, table_name=table_name, operation=operation,
            triggered_by=triggered_by, limit=limit, offset=offset,
        )
        _json_response(self, 200, data=entries)

    def _op_feedback_submit(self, conn, body):
        target_id = body.get("target_id", "")
        target_table = body.get("target_table", "")
        feedback_type = body.get("feedback_type", "")
        content = body.get("content", "")
        if not all([target_id, target_table, feedback_type, content]):
            return _json_response(self, 400, error="target_id, target_table, feedback_type, and content are required")
        fid = crud.create_feedback(conn, target_id, target_table, feedback_type, content)
        _json_response(self, 201, data={"id": fid})

    def _op_views_list(self, conn):
        views = crud.list_views(conn)
        _json_response(self, 200, data=views)

    def _op_view_create(self, conn, body):
        name = body.get("name", "")
        center_node_id = body.get("center_node_id", "")
        center_node_table = body.get("center_node_table", "")
        if not all([name, center_node_id, center_node_table]):
            return _json_response(self, 400, error="name, center_node_id, center_node_table are required")
        vid = crud.create_view(
            conn, name, center_node_id, center_node_table,
            depth_limit=body.get("depth_limit", 2),
            filters=body.get("filters"),
            layout_hints=body.get("layout_hints"),
        )
        _json_response(self, 201, data={"id": vid})

    def _op_workspaces_list(self, conn):
        workspaces = crud.list_workspaces(conn)
        _json_response(self, 200, data=workspaces)

    def _op_watcher_status(self, conn):
        enabled = crud.get_config_value(conn, "markdown_watch_enabled", "false")
        inbox = crud.get_config_value(conn, "markdown_inbox_path", "")
        pending = 0
        if inbox and os.path.isdir(inbox):
            pending = len([f for f in os.listdir(inbox) if f.endswith('.md')])
        _json_response(self, 200, data={
            "enabled": enabled == "true",
            "inbox_path": inbox,
            "files_pending": pending,
            "watcher_running": _file_watcher is not None,
        })

    def _op_markdown_submit(self, conn, body):
        text = body.get("text", "")
        if not text:
            return _json_response(self, 400, error="'text' is required")
        result = process_markdown_document(conn, text)
        status_code = 201 if result.get("status") == "ok" else 400
        _json_response(self, status_code, data=result)

    def _op_markdown_batch(self, conn, body):
        documents = body.get("documents", [])
        if not documents:
            return _json_response(self, 400, error="'documents' array is required")
        results = []
        for doc in documents:
            result = process_markdown_document(conn, doc)
            results.append(result)
        _json_response(self, 200, data={"results": results, "total": len(results)})

    def _op_markdown_reverse(self, conn, table, record_id):
        md = reverse_generate_markdown(conn, table, record_id)
        if md is None:
            return _json_response(self, 404, error="Record not found or not reversible")
        _json_response(self, 200, data={"markdown": md})

    def _op_memory_create(self, conn, tier, body):
        content = body.get("content", "")
        if not content:
            return _json_response(self, 400, error="'content' is required")
        emb = embedding_to_blob(generate_embedding(content))
        agent_id = body.get("agent_id", "default")
        if tier == "short":
            source = body.get("source", "conversation")
            mid = crud.create_short_term_memory(conn, content, source, embedding=emb, agent_id=agent_id)
        elif tier == "mid":
            category = body.get("category", "observation")
            confidence = float(body.get("confidence", 0.5))
            mid = crud.create_midterm_memory(conn, content, embedding=emb, confidence=confidence, category=category, agent_id=agent_id)
        elif tier == "long":
            category = body.get("category", "fact")
            confidence = float(body.get("confidence", 0.9))
            provenance = body.get("provenance", "user_authored")
            mid = crud.create_long_term_memory(conn, content, embedding=emb, confidence=confidence, category=category, provenance=provenance, agent_id=agent_id)
        else:
            return _json_response(self, 400, error=f"Invalid tier: {tier}")
        _json_response(self, 201, data={"id": mid, "tier": tier})

    def _op_skill_create(self, conn, body):
        name = body.get("name", "")
        description = body.get("description", "")
        execution_type = body.get("execution_type", "prompt_template")
        if not name or not description:
            return _json_response(self, 400, error="'name' and 'description' are required")
        emb = embedding_to_blob(generate_embedding(description))
        sid = crud.create_skill(conn, name, description, execution_type, embedding=emb,
                                input_schema=body.get("input_schema"), output_schema=body.get("output_schema"))
        _json_response(self, 201, data={"id": sid})

    def _op_entity_create(self, conn, body):
        canonical_name = body.get("canonical_name", "")
        entity_type = body.get("entity_type", "concept")
        if not canonical_name:
            return _json_response(self, 400, error="'canonical_name' is required")
        emb = embedding_to_blob(generate_embedding(canonical_name))
        aliases = body.get("aliases", [])
        eid = crud.create_entity(conn, canonical_name, entity_type, embedding=emb, aliases=aliases if aliases else None)
        _json_response(self, 201, data={"id": eid})

    def _op_agents_list(self, conn):
        agents = crud.list_agents(conn)
        _json_response(self, 200, data=agents)

    def _op_agent_create(self, conn, body):
        agent_id = body.get("id", "")
        name = body.get("name", "")
        if not agent_id or not name:
            return _json_response(self, 400, error="'id' and 'name' are required")
        description = body.get("description")
        config = body.get("config")
        crud.create_agent(conn, agent_id, name, description=description, config=config)
        _json_response(self, 201, data={"id": agent_id})

    def _op_agent_rotate_key(self, conn, agent_id):
        import secrets
        agent = crud.get_agent(conn, agent_id)
        if not agent:
            return _json_response(self, 404, error="Agent not found")
        config = agent.get("config") or {}
        if isinstance(config, str):
            import json as _json
            config = _json.loads(config) if config else {}
        new_key = secrets.token_urlsafe(32)
        config["api_key"] = new_key
        crud.update_agent(conn, agent_id, config=json.dumps(config))
        _json_response(self, 200, data={"agent_id": agent_id, "api_key": new_key,
                                        "note": "Store this key; it will not be shown again."})

    def _op_notifications_list(self, conn, qp):
        read = qp.get("read", [None])[0]
        priority = qp.get("priority", [None])[0]
        agent_id = qp.get("agent_id", [None])[0]
        limit = int(qp.get("limit", [100])[0])
        read_val = None
        if read is not None and read != '':
            read_val = int(read)
        notifications = crud.list_notifications(
            conn, read=read_val, priority=priority,
            agent_id=agent_id, limit=limit,
        )
        _json_response(self, 200, data=notifications)

    def _op_scheduled_tasks_list(self, conn, qp):
        status = qp.get("status", [None])[0]
        agent_id = qp.get("agent_id", [None])[0]
        limit = int(qp.get("limit", [100])[0])
        offset = int(qp.get("offset", [0])[0])
        tasks = crud.list_scheduled_tasks(
            conn, status=status, agent_id=agent_id, limit=limit, offset=offset
        )
        _json_response(self, 200, data=tasks)

    def _op_scheduled_task_detail(self, conn, task_id):
        task = crud.get_scheduled_task(conn, task_id)
        if not task:
            return _json_response(self, 404, error="Scheduled task not found")
        _json_response(self, 200, data=task)

    def _op_scheduled_task_create(self, conn, body):
        name = body.get("name", "")
        action_type = body.get("action_type", "")
        if not name or not action_type:
            return _json_response(self, 400, error="'name' and 'action_type' are required")
        try:
            interval_seconds = int(body.get("interval_seconds", 0))
        except (TypeError, ValueError):
            return _json_response(self, 400, error="'interval_seconds' must be an integer")
        if interval_seconds <= 0:
            return _json_response(self, 400, error="'interval_seconds' must be greater than 0")
        next_run_at = body.get("next_run_at") or compute_next_run(interval_seconds)
        task_id = crud.create_scheduled_task(
            conn,
            name=name,
            description=body.get("description"),
            agent_id=body.get("agent_id", "default"),
            action_type=action_type,
            schedule_type=body.get("schedule_type", "interval"),
            interval_seconds=interval_seconds,
            payload_json=body.get("payload_json", body.get("payload")),
            status=body.get("status", "active"),
            next_run_at=next_run_at,
        )
        _json_response(self, 201, data={"id": task_id, "next_run_at": next_run_at})

    def _op_scheduled_task_update(self, conn, task_id, body):
        if not crud.get_scheduled_task(conn, task_id):
            return _json_response(self, 404, error="Scheduled task not found")
        updates = dict(body)
        if "interval_seconds" in updates and "next_run_at" not in updates:
            try:
                updates["interval_seconds"] = int(updates["interval_seconds"])
            except (TypeError, ValueError):
                return _json_response(self, 400, error="'interval_seconds' must be an integer")
            updates["next_run_at"] = compute_next_run(updates["interval_seconds"])
        result = crud.update_scheduled_task(conn, task_id, **updates)
        _json_response(self, 200, data={"id": task_id, "updated": result})

    def _op_scheduler_status(self, conn):
        _json_response(self, 200, data={
            "enabled": crud.get_config_value(conn, "scheduler_enabled", "true") == "true",
            "poll_interval_seconds": int(crud.get_config_value(conn, "scheduler_poll_interval_seconds", "5")),
            "runner_started": _task_scheduler is not None,
            "last_result": _task_scheduler.last_result if _task_scheduler else None,
        })


def _run_integrity_check(conn):
    """Scan polymorphic reference columns for orphaned IDs."""
    from agentdb.schema import CONTENT_TABLES
    orphans_found = 0
    orphans_detail = []

    for poly_table in ("relations", "tag_assignments", "feedback"):
        if poly_table == "relations":
            id_cols = [("source_id", "source_table"), ("target_id", "target_table")]
        elif poly_table == "tag_assignments":
            id_cols = [("target_id", "target_table")]
        else:
            id_cols = [("target_id", "target_table")]

        for id_col, table_col in id_cols:
            rows = conn.execute(
                f"SELECT id, {id_col}, {table_col} FROM {poly_table}"
            ).fetchall()
            for row in rows:
                ref_id = row[id_col]
                ref_table = row[table_col]
                if ref_table not in CONTENT_TABLES:
                    continue
                exists = conn.execute(
                    f"SELECT 1 FROM {ref_table} WHERE id = ?", (ref_id,)
                ).fetchone()
                if not exists:
                    orphans_found += 1
                    orphans_detail.append({
                        "poly_table": poly_table,
                        "poly_id": row["id"],
                        "references": f"{ref_table}.{ref_id}",
                    })
                    orphan_mode = crud.get_config_value(conn, "orphan_handling_mode", "flag")
                    if orphan_mode == "auto":
                        conn.execute(f"DELETE FROM {poly_table} WHERE id = ?", (row["id"],))
                    crud.create_audit_entry(
                        conn, poly_table, row["id"], "delete" if orphan_mode == "auto" else "update",
                        "manual",
                        after_snapshot={"orphan_detected": True, "references": f"{ref_table}.{ref_id}"},
                    )
    conn.commit()
    return {
        "orphans_found": orphans_found,
        "orphans": orphans_detail[:50],
        "action": crud.get_config_value(conn, "orphan_handling_mode", "flag"),
    }


def run_server(db_path, host="127.0.0.1", port=8420):
    """
    Start the AgentDB HTTP server.

    Args:
        db_path: Path to the SQLite database file.
        host: Bind address (default localhost).
        port: Port number (default 8420).
    """
    global _db_path, _start_time, _file_watcher, _task_scheduler
    _db_path = db_path
    _start_time = time.time()

    conn = get_connection(db_path)
    ensure_scheduler_schema(conn)
    conn.close()

    # Start markdown file watcher if enabled
    try:
        conn = get_connection(db_path)
        watch_enabled = crud.get_config_value(conn, "markdown_watch_enabled", "false")
        conn.close()
        if watch_enabled == "true":
            _file_watcher = MarkdownFileWatcher(db_path)
            _file_watcher.start()
            print("Markdown file watcher started")
    except Exception as e:
        print(f"Warning: Could not start file watcher: {e}")

    try:
        _task_scheduler = ScheduledTaskRunner(db_path)
        _task_scheduler.start()
        print("Scheduled task runner started")
    except Exception as e:
        print(f"Warning: Could not start scheduled task runner: {e}")

    server = HTTPServer((host, port), AgentDBHandler)
    print(f"AgentDB server running at http://{host}:{port}")
    print(f"Database: {db_path}")
    print(f"Operator API: http://{host}:{port}/api/")
    print(f"Agent API:    http://{host}:{port}/api/agent/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down AgentDB server...")
        if _file_watcher:
            _file_watcher.stop()
            print("File watcher stopped")
        if _task_scheduler:
            _task_scheduler.stop()
            print("Scheduled task runner stopped")
        server.shutdown()
