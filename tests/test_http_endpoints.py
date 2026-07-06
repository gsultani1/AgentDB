"""
End-to-end HTTP contract tests against a real `swadb serve` subprocess.

One server per session, fresh DB in a tempdir. Every documented endpoint
gets hit and its response shape asserted — this catches the CRUD-shape
mismatches in HTTP handlers that unit tests miss. Where the docs and the
code disagree, tests assert what the CODE returns and flag the mismatch
in a comment (doc bugs shouldn't fail the suite).

Endpoints that need a live LLM provider or outbound network are skipped,
not mocked.
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.slow


# ══════════════════════════════════════════════════════════════
# Plumbing
# ══════════════════════════════════════════════════════════════

def _free_port():
    # Bind-then-close: the OS hands us a port nothing else is using.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _raw_request(method, url, body=None, timeout=30):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        # Error statuses still carry the JSON envelope — read it, don't raise.
        return e.code, e.read(), e.headers.get("Content-Type", "")


def _call(srv, method, path, body=None, timeout=30):
    """Request against the session server; asserts the JSON envelope invariant."""
    status, raw, ctype = _raw_request(method, srv.base + path, body, timeout)
    assert "application/json" in ctype, \
        f"{method} {path}: expected JSON, got {ctype!r}: {raw[:200]!r}"
    env = json.loads(raw)
    # Every JSON response uses exactly this envelope (server._json_response).
    assert set(env) == {"status", "data", "error"}, \
        f"{method} {path}: bad envelope keys {sorted(env)}"
    expected = "ok" if env["error"] is None else "error"
    assert env["status"] == expected, f"{method} {path}: {env}"
    return status, env


def _ok(srv, method, path, body=None, expect=200, timeout=30):
    """_call + status assert; returns just the data payload."""
    status, env = _call(srv, method, path, body, timeout)
    assert status == expect, f"{method} {path} -> {status}: {env['error']}"
    return env["data"]


def _uniq(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


# ══════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def server(tmp_path_factory):
    root = tmp_path_factory.mktemp("http-endpoints")
    db_path = str(root / "swadb-test.db")

    from swadb import crud
    from swadb.database import initialize_database
    conn = initialize_database(db_path)
    # MCP would grab its fixed default port (8421) in every server instance,
    # and the scheduler adds background writes — both off for test isolation.
    crud.set_config(conn, "mcp_enabled", "false")
    crud.set_config(conn, "scheduler_enabled", "false")
    conn.close()

    # Inherits the HF offline vars conftest sets when the model is cached.
    env = dict(os.environ)

    port = _free_port()
    log_path = root / "server.log"
    log_file = open(log_path, "wb")

    def _startup_failure(reason):
        # Close our write handle before reading, and put the log tail in the
        # error — it's the only thing that says why the server died.
        log_file.close()
        tail = log_path.read_bytes()[-2000:].decode("utf-8", "replace")
        return RuntimeError(f"{reason}\n--- server log tail ---\n{tail}")

    # -u: unbuffered, so the warmup completion line hits the log promptly.
    proc = subprocess.Popen(
        [sys.executable, "-u", "-m", "swadb", "--db", db_path,
         "serve", "--host", "127.0.0.1", "--port", str(port)],
        stdout=log_file, stderr=subprocess.STDOUT, env=env,
    )
    srv = SimpleNamespace(base=f"http://127.0.0.1:{port}", root=root,
                          db=db_path, log_path=log_path)

    # /api/agent/health never touches the embedding model, so it answers long
    # before the warmup thread finishes — but allow 60s for a cold interpreter.
    deadline = time.time() + 60
    ready = False
    while time.time() < deadline:
        if proc.poll() is not None:
            raise _startup_failure(f"server exited early (code {proc.returncode})")
        try:
            status, _, _ = _raw_request("GET", srv.base + "/api/agent/health", timeout=5)
            if status == 200:
                ready = True
                break
        except OSError:
            pass
        time.sleep(0.25)
    if not ready:
        proc.kill()
        proc.wait(timeout=10)
        raise _startup_failure("server never became ready within 60s")

    yield srv

    # Kill before tempdir cleanup: Windows can't unlink the .db/-wal files
    # while the server process still holds handles.
    try:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
    finally:
        log_file.close()


@pytest.fixture(scope="session")
def embeddings(server):
    """
    Gate embedding tests on the server's model warmup having FINISHED.

    get_model() is lock-guarded now, so the old double-load poisoning can't
    happen — but waiting for the warmup completion line keeps the first
    embedding test from stalling behind a cold model load, and the probe
    ingest below skips the embedding suite cleanly when the model can't
    load at all (e.g. uncached machine with no network). Tests that embed
    depend on this fixture.
    """
    deadline = time.time() + 180
    while time.time() < deadline:
        log = server.log_path.read_bytes()
        if b"Embedding model pre-warmed" in log or b"Embedding warm-up failed" in log:
            break
        time.sleep(0.5)

    status, env = _call(server, "POST", "/api/agent/ingest",
                        {"content": _uniq("warmup observation")}, timeout=180)
    if status != 201:
        pytest.skip(f"embedding model unavailable (ingest -> {status}: {env['error']})")
    return True


def _make_short_memory(srv, content=None):
    data = _ok(srv, "POST", "/api/memories/short",
               {"content": content or _uniq("short mem"), "source": "tool_output"},
               expect=201, timeout=60)
    return data["id"]


# ══════════════════════════════════════════════════════════════
# Health / stats
# ══════════════════════════════════════════════════════════════

def test_agent_health(server):
    data = _ok(server, "GET", "/api/agent/health")
    assert data["database_ok"] is True
    assert isinstance(data["sidecar_uptime_seconds"], (int, float))
    assert "embedding_model" in data
    assert "last_consolidation" in data


def test_operator_health_doc_mismatch(server):
    # DOC MISMATCH: http_api.md documents GET /api/health, but no route
    # exists while unlocked — it's only answered inline in locked mode.
    status, env = _call(server, "GET", "/api/health")
    assert status == 404
    assert "Not found" in env["error"]


def test_stats(server):
    data = _ok(server, "GET", "/api/stats")
    for key in ("short_term_memories", "midterm_memories", "long_term_memories",
                "skills", "entities", "goals", "sessions", "workspaces",
                "unresolved_contradictions", "pending_feedback", "active_goals"):
        assert isinstance(data[key], int), key
    assert isinstance(data["llm_provider"], str)
    assert isinstance(data["agents"], int)
    # Doc calls this "queue depths"; it's really the cache metrics sub-dict
    # (the int table count gets overwritten by the dict).
    assert isinstance(data["query_cache"], dict)


# ══════════════════════════════════════════════════════════════
# Memories: CRUD lifecycle per tier
# ══════════════════════════════════════════════════════════════

_TIER_CREATE_BODIES = {
    # category values are schema CHECK-constrained per tier.
    "short": {"source": "tool_output"},
    "mid": {"category": "observation", "confidence": 0.5},
    "long": {"category": "fact", "confidence": 0.9, "provenance": ["test"]},
}


@pytest.mark.parametrize("tier", ["short", "mid", "long"])
def test_memory_lifecycle(server, embeddings, tier):
    content = _uniq(f"{tier} lifecycle memory")
    body = {"content": content, **_TIER_CREATE_BODIES[tier]}

    created = _ok(server, "POST", f"/api/memories/{tier}", body, expect=201, timeout=60)
    assert isinstance(created["id"], str)
    assert created["tier"] == tier
    mem_id = created["id"]

    # List: default limit is 100 (doc says 50) and ?status= is ignored.
    listed = _ok(server, "GET", f"/api/memories/{tier}?limit=100")
    assert isinstance(listed, list)
    ours = [m for m in listed if m["id"] == mem_id]
    assert len(ours) == 1
    assert "embedding" not in ours[0]

    detail = _ok(server, "GET", f"/api/memories/{tier}/{mem_id}")
    assert detail["content"] == content
    assert "embedding" not in detail
    for key in ("relations", "tags", "feedback"):
        assert isinstance(detail[key], list), key

    new_content = content + " (updated)"
    updated = _ok(server, "PUT", f"/api/memories/{tier}/{mem_id}", {"content": new_content})
    assert updated == {"id": mem_id, "updated": True}
    assert _ok(server, "GET", f"/api/memories/{tier}/{mem_id}")["content"] == new_content

    deleted = _ok(server, "DELETE", f"/api/memories/{tier}/{mem_id}")
    assert deleted == {"deleted": mem_id}
    # DELETE is 200 even for bogus ids, so deletion is proven by the 404 here.
    status, _ = _call(server, "GET", f"/api/memories/{tier}/{mem_id}")
    assert status == 404


def test_memory_invalid_tier(server):
    status, env = _call(server, "GET", "/api/memories/bogus")
    assert status == 400
    assert "Invalid tier" in env["error"]


def test_memory_search(server, embeddings):
    marker = _uniq("searchable fact about zebras")
    _make_short_memory(server, marker)
    data = _ok(server, "POST", "/api/memories/search",
               {"query": "zebras", "tiers": ["short"], "limit": 5}, timeout=60)
    # Shape is a dict keyed by tier, NOT a flat list.
    assert isinstance(data, dict)
    assert set(data) == {"short"}
    assert isinstance(data["short"], list)
    for row in data["short"]:
        assert "similarity_score" in row
        assert "embedding" not in row
    # Not just shape: the memory ingested above must actually come back,
    # otherwise a search that always returns [] passes vacuously.
    assert any(marker in row["content"] for row in data["short"])


# ══════════════════════════════════════════════════════════════
# Memories: batch + pin endpoints
# ══════════════════════════════════════════════════════════════

def test_batch_pin(server, embeddings):
    ids = [_make_short_memory(server) for _ in range(2)]
    data = _ok(server, "POST", "/api/memories/batch/pin",
               {"ids": ids, "memory_table": "short_term_memory"})
    assert data["pinned"] == 2
    assert isinstance(data["pin_ids"], list) and len(data["pin_ids"]) == 2


def test_batch_tag(server, embeddings):
    ids = [_make_short_memory(server) for _ in range(2)]
    tag = _uniq("tag")
    data = _ok(server, "POST", "/api/memories/batch/tag",
               {"ids": ids, "memory_table": "short_term_memory", "tag_name": tag})
    assert data["tagged"] == 2
    assert isinstance(data["tag_id"], str)
    assert data["tag_name"] == tag


def test_batch_promote(server, embeddings):
    ids = [_make_short_memory(server) for _ in range(2)]
    data = _ok(server, "POST", "/api/memories/batch/promote",
               {"ids": ids, "memory_table": "short_term_memory"})
    assert data["promoted"] == 2
    assert isinstance(data["new_ids"], list) and len(data["new_ids"]) == 2

    status, env = _call(server, "POST", "/api/memories/batch/promote",
                        {"ids": ids, "memory_table": "long_term_memory"})
    assert status == 400  # nothing above long


def test_batch_delete(server, embeddings):
    ids = [_make_short_memory(server) for _ in range(2)]
    data = _ok(server, "POST", "/api/memories/batch/delete",
               {"ids": ids, "memory_table": "short_term_memory"})
    # Count is len(ids), not rows actually deleted.
    assert data == {"deleted": 2}
    # STM batch delete is a soft delete (status -> 'expired'), unlike the
    # single DELETE endpoint which removes the row.
    detail = _ok(server, "GET", f"/api/memories/short/{ids[0]}")
    assert detail["status"] == "expired"


def test_pinned_list_shadowed_doc_mismatch(server):
    # DOC MISMATCH / ROUTING BUG: GET /api/memories/pinned is captured by
    # the /api/memories/{tier} pattern first, so the documented pinned-list
    # handler is dead code and this returns 400.
    status, env = _call(server, "GET", "/api/memories/pinned")
    assert status == 400
    assert "Invalid tier" in env["error"]


def test_pin_lifecycle(server, embeddings):
    mem_id = _make_short_memory(server)

    # Regression guard: this endpoint used to 500 on every call (handler
    # forwarded reason= to crud.pin_memory, whose parameter is 'label').
    data = _ok(server, "POST", "/api/memories/pin",
               {"memory_id": mem_id, "memory_table": "short_term_memory",
                "label": "pinned by http test"},
               expect=201)
    pin_id = data["id"]

    data = _ok(server, "PUT", f"/api/memories/pinned/{pin_id}/priority", {"priority": 7})
    assert data == {"id": pin_id, "priority": 7}

    # Key is 'unpinned', not 'deleted'.
    data = _ok(server, "DELETE", f"/api/memories/pinned/{pin_id}")
    assert data == {"unpinned": pin_id}


# ══════════════════════════════════════════════════════════════
# Entities / relations
# ══════════════════════════════════════════════════════════════

def test_entity_lifecycle(server, embeddings):
    name = _uniq("Entity")
    created = _ok(server, "POST", "/api/entities",
                  {"canonical_name": name, "entity_type": "concept"},
                  expect=201, timeout=60)
    ent_id = created["id"]
    assert isinstance(ent_id, str)

    # Filter param is ?type=, not the documented ?entity_type=.
    listed = _ok(server, "GET", "/api/entities?type=concept&limit=100")
    assert isinstance(listed, list)
    ours = [e for e in listed if e["id"] == ent_id]
    assert len(ours) == 1
    assert "embedding" not in ours[0]

    # DOC MISMATCH: plain GET /api/entities/{id} is documented but unrouted —
    # only the /graph and /detail variants exist.
    status, _ = _call(server, "GET", f"/api/entities/{ent_id}")
    assert status == 404

    graph = _ok(server, "GET", f"/api/entities/{ent_id}/graph?depth=1")
    assert isinstance(graph["nodes"], list)
    assert isinstance(graph["edges"], list)
    assert any(n["id"] == ent_id for n in graph["nodes"])

    detail = _ok(server, "GET", f"/api/entities/{ent_id}/detail")
    assert detail["entity"]["id"] == ent_id
    for key in ("memories", "relations", "co_occurring", "skill_executions"):
        assert isinstance(detail[key], list), key

    updated = _ok(server, "PUT", f"/api/entities/{ent_id}",
                  {"entity_type": "person"})
    assert updated == {"id": ent_id, "updated": True}

    relations = _ok(server, "GET", f"/api/relations/{ent_id}")
    assert isinstance(relations, list)

    deleted = _ok(server, "DELETE", f"/api/entities/{ent_id}")
    assert deleted == {"deleted": ent_id}


def test_entity_graph_missing(server):
    status, _ = _call(server, "GET", f"/api/entities/{_uniq('nope')}/graph")
    assert status == 404


# ══════════════════════════════════════════════════════════════
# Goals
# ══════════════════════════════════════════════════════════════

def test_goal_lifecycle(server, embeddings):
    desc = _uniq("goal description")
    # Doc also lists criteria?/status? body fields; the handler ignores them.
    created = _ok(server, "POST", "/api/goals",
                  {"description": desc, "priority": 3}, expect=201, timeout=60)
    goal_id = created["id"]

    listed = _ok(server, "GET", "/api/goals")
    ours = [g for g in listed if g["id"] == goal_id]
    assert len(ours) == 1
    assert "embedding" not in ours[0]

    updated = _ok(server, "PUT", f"/api/goals/{goal_id}", {"status": "completed"})
    assert updated == {"id": goal_id, "updated": True}

    deleted = _ok(server, "DELETE", f"/api/goals/{goal_id}")
    assert deleted == {"deleted": goal_id}


# ══════════════════════════════════════════════════════════════
# Skills + executions
# ══════════════════════════════════════════════════════════════

def _make_skill(server, description=None):
    return _ok(server, "POST", "/api/skills",
               {"name": _uniq("skill"),
                "description": description or _uniq("does a thing")},
               expect=201, timeout=60)["id"]


def test_skill_lifecycle(server, embeddings):
    skill_id = _make_skill(server)

    listed = _ok(server, "GET", "/api/skills")
    ours = [s for s in listed if s["id"] == skill_id]
    assert len(ours) == 1
    assert "embedding" not in ours[0]

    impls = _ok(server, "GET", f"/api/skills/{skill_id}/implementations")
    assert impls == []  # fresh skill has no implementations

    status, _ = _call(server, "POST", f"/api/skills/{skill_id}/rollback/99")
    assert status == 404  # version doesn't exist

    updated = _ok(server, "PUT", f"/api/skills/{skill_id}",
                  {"description": "updated description"})
    assert updated == {"id": skill_id, "updated": True}

    status, env = _call(server, "PUT", f"/api/skills/{skill_id}", {"bogus_field": 1})
    assert status == 400  # crud filters all fields out -> 'No valid fields'

    deleted = _ok(server, "DELETE", f"/api/skills/{skill_id}")
    assert deleted == {"deleted": skill_id}


def test_skill_executions(server, embeddings):
    status, _ = _call(server, "POST", "/api/skill-executions", {})
    assert status == 400  # skill_id required

    skill_id = _make_skill(server)
    data = _ok(server, "POST", "/api/skill-executions",
               {"skill_id": skill_id, "inputs": {}})
    assert isinstance(data, dict)  # execute_skill result dict

    listed = _ok(server, "GET", "/api/skill-executions")  # undocumented but routed
    assert isinstance(listed, list)

    # DOC MISMATCH: DELETE /api/skill-executions/{id} is documented but no
    # such route exists.
    status, _ = _call(server, "DELETE", f"/api/skill-executions/{_uniq('x')}")
    assert status == 404


def test_agent_skill_execute(server, embeddings):
    status, _ = _call(server, "POST", "/api/agent/skill/execute", {})
    assert status == 400  # skill_id required

    status, _ = _call(server, "POST", "/api/agent/skill/execute",
                      {"skill_id": _uniq("missing")})
    assert status == 404  # skill not found

    skill_id = _make_skill(server)
    status, env = _call(server, "POST", "/api/agent/skill/execute",
                        {"skill_id": skill_id})
    assert status == 404  # no active implementation on a fresh skill


def test_agent_skill_match(server, embeddings):
    # Query with the exact created description: any similarity threshold or
    # top-K cutoff still has to return the ~1.0-cosine match, so the test
    # can't pass vacuously on an always-empty matcher and can't flake on
    # the random _uniq suffix.
    desc = _uniq("matchable skill that reverses strings")
    skill_id = _make_skill(server, description=desc)
    data = _ok(server, "POST", "/api/agent/skill/match",
               {"description": desc}, timeout=60)
    assert isinstance(data, list)
    for row in data:
        assert "similarity_score" in row
    assert any(row.get("id") == skill_id or row.get("skill_id") == skill_id
               for row in data)


# ══════════════════════════════════════════════════════════════
# Workspaces
# ══════════════════════════════════════════════════════════════

def test_workspace_lifecycle(server, embeddings, tmp_path):
    # embeddings fixture: workspace scan embeds file contents.
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    (ws_dir / "note.md").write_text("hello", encoding="utf-8")

    created = _ok(server, "POST", "/api/workspaces",
                  {"name": _uniq("ws"), "root_path": str(ws_dir)}, expect=201)
    ws_id = created["id"]

    listed = _ok(server, "GET", "/api/workspaces")
    ours = [w for w in listed if w["id"] == ws_id]
    assert len(ours) == 1
    assert isinstance(ours[0]["file_count"], int)
    assert isinstance(ours[0]["file_types"], dict)

    updated = _ok(server, "PUT", f"/api/workspaces/{ws_id}", {"name": _uniq("ws2")})
    assert updated["id"] == ws_id
    assert "updated" in updated

    scan = _ok(server, "POST", f"/api/workspaces/{ws_id}/scan", timeout=60)
    assert isinstance(scan, dict)

    # Documented ?file_type=&limit= are ignored by the handler.
    files = _ok(server, "GET", f"/api/workspaces/{ws_id}/files")
    assert isinstance(files, list)
    for f in files:
        assert "embedding" not in f

    scan_all = _ok(server, "POST", "/api/workspaces/scan", timeout=60)
    assert isinstance(scan_all["workspaces"], list)

    deleted = _ok(server, "DELETE", f"/api/workspaces/{ws_id}")
    assert deleted == {"deleted": ws_id}


def test_workspace_bad_root_path(server):
    status, _ = _call(server, "POST", "/api/workspaces",
                      {"name": _uniq("ws"), "root_path": "C:/does/not/exist/" + uuid.uuid4().hex})
    assert status == 400


# ══════════════════════════════════════════════════════════════
# File access grants + grant-gated system endpoints
# ══════════════════════════════════════════════════════════════

def test_file_access_grants_and_system_files(server, tmp_path):
    granted = tmp_path / "granted"
    granted.mkdir()
    target = granted / "readme.txt"
    target.write_text("grant me", encoding="utf-8")

    ungranted = tmp_path / "ungranted"
    ungranted.mkdir()
    secret = ungranted / "secret.txt"
    secret.write_text("no access", encoding="utf-8")

    grant = _ok(server, "POST", "/api/file-access-grants",
                {"directory_path": str(granted), "permission": "read_write"},
                expect=201)
    grant_id = grant["id"]

    grants = _ok(server, "GET", "/api/file-access-grants")
    assert any(g["id"] == grant_id for g in grants)

    q = urllib.parse.quote(str(target))
    data = _ok(server, "GET", f"/api/system/file/read?path={q}")
    assert isinstance(data, dict)

    q = urllib.parse.quote(str(granted))
    data = _ok(server, "GET", f"/api/system/file/list?path={q}")
    assert isinstance(data, dict)

    data = _ok(server, "GET", f"/api/system/file/stat?path={q}")
    assert data["is_dir"] is True
    assert isinstance(data["size_bytes"], int)

    status, _ = _call(server, "GET",
                      f"/api/system/file/stat?path={urllib.parse.quote(str(granted / 'missing.txt'))}")
    assert status == 404

    written = granted / "written.txt"
    data = _ok(server, "POST", "/api/system/file/write",
               {"path": str(written), "content": "written by test"})
    assert isinstance(data, dict)
    assert written.read_text(encoding="utf-8") == "written by test"

    # No covering grant -> denied.
    q = urllib.parse.quote(str(secret))
    status, _ = _call(server, "GET", f"/api/system/file/read?path={q}")
    assert status == 403

    deleted = _ok(server, "DELETE", f"/api/file-access-grants/{grant_id}")
    assert deleted == {"deleted": grant_id}


def test_shell_execute_disabled_by_default(server):
    # meta_config shell_access_enabled defaults 'false'.
    status, _ = _call(server, "POST", "/api/system/shell/execute",
                      {"command": "echo nope"})
    assert status == 403

    log = _ok(server, "GET", "/api/shell-log")
    assert isinstance(log, list)


# ══════════════════════════════════════════════════════════════
# Encryption (plaintext DB — status + unlock smoke only)
# ══════════════════════════════════════════════════════════════

def test_encryption_enable_disable_rekey_http():
    # tests/test_encryption.py covers encrypt/decrypt/rekey at the library
    # level only — the HTTP handlers for POST /api/encryption/enable,
    # /disable, and /rekey have no coverage here because they would encrypt
    # the shared session DB. Handler-level wiring bugs (the class this suite
    # exists to catch) can hide in them until a dedicated encrypted-server
    # test exists: boot a second short-lived server on its own tempdir DB
    # under @pytest.mark.encryption and drive enable -> rekey -> disable.
    pytest.skip("needs a dedicated encrypted-server fixture; "
                "library layer covered in test_encryption.py")


def test_locked_mode_contract():
    # Documented locked-mode behavior (http_api.md: /api/health answers
    # {status: locked}; other endpoints return 423 until
    # /api/encryption/unlock) is unexercisable against the shared plaintext
    # session server. Cover together with the encrypted-server fixture above.
    pytest.skip("needs an encrypted-DB server started without a passphrase")


def test_encryption_status_and_unlock(server):
    data = _ok(server, "GET", "/api/encryption/status")
    for key in ("sqlcipher_available", "passphrase_set", "library",
                "encryption_enabled_config", "db_path", "db_encrypted"):
        assert key in data, key
    assert data["db_encrypted"] is False

    data = _ok(server, "POST", "/api/encryption/unlock", {"passphrase": "whatever"})
    assert data["unlocked"] is True
    assert data.get("already_unlocked") is True  # plaintext DB variant


# ══════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════

def test_config_crud(server):
    listed = _ok(server, "GET", "/api/config")
    assert isinstance(listed, list)
    assert all("key" in row and "value" in row for row in listed)

    key = _uniq("test_config_key")
    data = _ok(server, "PUT", f"/api/config/{key}", {"value": 42})
    assert data == {"key": key, "value": "42"}  # always stringified

    row = _ok(server, "GET", f"/api/config/{key}")
    assert row["key"] == key
    assert row["value"] == "42"

    status, _ = _call(server, "GET", f"/api/config/{_uniq('missing_key')}")
    assert status == 404


def test_alert_rules(server):
    data = _ok(server, "POST", "/api/config/alert-rules",
               {"rules": [{"metric": "short_term_memories", "threshold": 10}]})
    assert data == {"saved": 1}

    # DOC MISMATCH / ROUTING BUG: GET /api/config/alert-rules is shadowed by
    # the /api/config/{key} pattern; rules live under 'custom_alert_rules',
    # so the documented GET 404s even right after a successful save.
    status, env = _call(server, "GET", "/api/config/alert-rules")
    assert status == 404


# ══════════════════════════════════════════════════════════════
# Providers
# ══════════════════════════════════════════════════════════════

def test_provider_lifecycle(server):
    listed = _ok(server, "GET", "/api/providers")
    assert isinstance(listed, list)
    assert len(listed) >= 1  # bootstrap seeds a Default provider

    created = _ok(server, "POST", "/api/providers",
                  {"name": _uniq("prov"), "model": "claude-sonnet-4-5",
                   "api_key": "sk-test-abcd1234"}, expect=201)
    prov_id = created["id"]

    listed = _ok(server, "GET", "/api/providers")
    ours = [p for p in listed if p["id"] == prov_id]
    assert len(ours) == 1
    assert ours[0]["api_key"] == "****1234"  # masked, last 4 kept

    # Response key is 'updated', not the usual {id, updated: true}.
    data = _ok(server, "PUT", f"/api/providers/{prov_id}", {"model": "claude-opus-4-6"})
    assert data == {"updated": prov_id}

    deleted = _ok(server, "DELETE", f"/api/providers/{prov_id}")
    assert deleted == {"deleted": prov_id}


def test_provider_test_endpoint(server):
    pytest.skip("POST /api/providers/{id}/test makes a real LLM API call")


def test_ollama_discover_dead_endpoint(server):
    # Local dead port refuses instantly — deterministic, no external network.
    dead = f"http://127.0.0.1:{_free_port()}"
    data = _ok(server, "POST", "/api/providers/ollama/discover",
               {"endpoint": dead}, timeout=30)
    assert data["models"] == []
    assert "error" in data


# ══════════════════════════════════════════════════════════════
# Channels
# ══════════════════════════════════════════════════════════════

def test_channel_lifecycle(server):
    name = _uniq("channel")
    # Regression guard: POST used to 500 on every call — the handler passed
    # (channel_type, name) swapped plus credentials=/settings= kwargs that
    # crud.create_channel_config doesn't accept. HTTP 'credentials' and
    # 'settings' now land as sub-keys of the config JSON column.
    created = _ok(server, "POST", "/api/channels",
                  {"name": name, "channel_type": "email",
                   "credentials": {"imap_password": "hunter2"},
                   "settings": {"folder": "INBOX"}},
                  expect=201)
    ch_id = created["id"]

    listed = _ok(server, "GET", "/api/channels")
    ours = [c for c in listed if c["id"] == ch_id]
    assert len(ours) == 1
    assert ours[0]["name"] == name
    assert ours[0]["channel_type"] == "email"
    assert ours[0]["enabled"] is True

    detail = _ok(server, "GET", f"/api/channels/{ch_id}")
    assert detail["name"] == name
    assert detail["config"]["credentials"] == "****"
    assert detail["config"]["settings"] == {"folder": "INBOX"}
    # Credentials must not leak from either the detail or the list endpoint
    # (list used to return the config column unmasked).
    assert "hunter2" not in json.dumps(detail)
    assert "hunter2" not in json.dumps(listed)

    # Regression guard: PUT used to forward credentials/settings/enabled as
    # kwargs, which update_channel_config turns into "SET enabled = ?" —
    # no such columns -> OperationalError 500.
    updated = _ok(server, "PUT", f"/api/channels/{ch_id}",
                  {"name": name + "2", "settings": {"folder": "Archive"}})
    assert updated == {"id": ch_id, "updated": True}
    detail = _ok(server, "GET", f"/api/channels/{ch_id}")
    assert detail["name"] == name + "2"
    assert detail["config"]["settings"] == {"folder": "Archive"}
    # Merge, not replace: credentials survive a settings-only update.
    assert detail["config"]["credentials"] == "****"

    # 'enabled' is the HTTP alias for the is_active column.
    _ok(server, "PUT", f"/api/channels/{ch_id}", {"enabled": False})
    detail = _ok(server, "GET", f"/api/channels/{ch_id}")
    assert detail["enabled"] is False
    # Disabled channels drop out of the default list...
    listed = _ok(server, "GET", "/api/channels")
    assert not any(c["id"] == ch_id for c in listed)
    # ...but stay reachable with ?include_inactive=true.
    listed = _ok(server, "GET", "/api/channels?include_inactive=true")
    assert any(c["id"] == ch_id for c in listed)

    deleted = _ok(server, "DELETE", f"/api/channels/{ch_id}")
    assert deleted == {"deleted": ch_id}
    status, _ = _call(server, "GET", f"/api/channels/{ch_id}")
    assert status == 404


def test_channel_validation(server):
    status, _ = _call(server, "POST", "/api/channels", {"name": _uniq("ch")})
    assert status == 400  # channel_type required

    # Schema CHECK constraint surfaced as a 400, not an IntegrityError 500.
    status, _ = _call(server, "POST", "/api/channels",
                      {"name": _uniq("ch"), "channel_type": "carrier-pigeon"})
    assert status == 400

    status, _ = _call(server, "PUT", f"/api/channels/{_uniq('missing')}",
                      {"name": "x"})
    assert status == 404


def test_channel_messages(server):
    ch_id = _ok(server, "POST", "/api/channels",
                {"name": _uniq("msg-channel"), "channel_type": "sms"},
                expect=201)["id"]

    # Regression guard: handler used to pass external_id=/metadata= kwargs
    # that crud.create_channel_message doesn't accept -> 500. 'metadata'
    # now maps to the raw_payload column.
    created = _ok(server, "POST", f"/api/channels/{ch_id}/messages",
                  {"direction": "outbound", "content": "hello out",
                   "recipient": "+15550001111", "metadata": {"k": "v"}},
                  expect=201)
    assert isinstance(created["id"], str)
    _ok(server, "POST", f"/api/channels/{ch_id}/messages",
        {"direction": "inbound", "content": "hello in",
         "sender": "+15550002222"}, expect=201)

    msgs = _ok(server, "GET", f"/api/channels/{ch_id}/messages?limit=50")
    assert len(msgs) == 2

    # Regression guard: ?direction= used to 500 (kwarg missing from
    # crud.list_channel_messages).
    inbound = _ok(server, "GET",
                  f"/api/channels/{ch_id}/messages?direction=inbound")
    assert [m["content"] for m in inbound] == ["hello in"]

    status, _ = _call(server, "POST", f"/api/channels/{ch_id}/messages", {})
    assert status == 400  # content required
    status, _ = _call(server, "POST", f"/api/channels/{ch_id}/messages",
                      {"content": "x", "direction": "sideways"})
    assert status == 400  # direction CHECK surfaced as 400
    status, _ = _call(server, "POST",
                      f"/api/channels/{_uniq('missing')}/messages",
                      {"content": "orphan"})
    assert status == 404  # no orphan messages against deleted channels

    # DELETE cascades messages via the schema trigger.
    _ok(server, "DELETE", f"/api/channels/{ch_id}")
    msgs = _ok(server, "GET", f"/api/channels/{ch_id}/messages")
    assert msgs == []


# ══════════════════════════════════════════════════════════════
# Notifications
# ══════════════════════════════════════════════════════════════

def test_notifications(server):
    listed = _ok(server, "GET", "/api/notifications")
    assert isinstance(listed, list)

    # mark_notification_read is unconditional — 200 even for a bogus id.
    bogus = _uniq("notif")
    data = _ok(server, "PUT", f"/api/notifications/{bogus}/read")
    assert data == {"id": bogus, "read": True}

    data = _ok(server, "POST", "/api/notifications/dismiss")
    assert data == {"message": "Read notifications dismissed"}

    # Fresh DB has no notification_webhook_url configured.
    status, _ = _call(server, "POST", "/api/notifications/test-webhook")
    assert status == 400

    status, _ = _call(server, "POST", f"/api/notifications/{bogus}/deliver")
    assert status == 400  # no webhook URL configured

    data = _ok(server, "POST", "/api/notifications/deliver-pending")
    assert isinstance(data, dict)


# ══════════════════════════════════════════════════════════════
# Scheduled tasks + scheduler
# ══════════════════════════════════════════════════════════════

def test_scheduled_task_lifecycle(server):
    created = _ok(server, "POST", "/api/scheduled-tasks",
                  {"name": _uniq("task"), "action_type": "integrity_check",
                   "interval_seconds": 3600}, expect=201)
    task_id = created["id"]
    assert "next_run_at" in created

    listed = _ok(server, "GET", "/api/scheduled-tasks")
    assert any(t["id"] == task_id for t in listed)

    data = _ok(server, "PUT", f"/api/scheduled-tasks/{task_id}",
               {"interval_seconds": 7200})
    assert data["id"] == task_id
    assert "updated" in data

    status, _ = _call(server, "PUT", f"/api/scheduled-tasks/{_uniq('missing')}",
                      {"interval_seconds": 60})
    assert status == 404

    run = _ok(server, "POST", f"/api/scheduled-tasks/{task_id}/run", timeout=60)
    assert isinstance(run, dict)

    deleted = _ok(server, "DELETE", f"/api/scheduled-tasks/{task_id}")
    assert deleted == {"deleted": task_id}


def test_scheduler_status(server):
    data = _ok(server, "GET", "/api/scheduler/status")
    assert isinstance(data["enabled"], bool)
    assert isinstance(data["poll_interval_seconds"], int)
    assert isinstance(data["runner_started"], bool)
    assert "last_result" in data


# ══════════════════════════════════════════════════════════════
# Agent API
# ══════════════════════════════════════════════════════════════

def test_agent_ingest(server, embeddings):
    data = _ok(server, "POST", "/api/agent/ingest",
               {"content": _uniq("observed thing"), "source": "tool_output"},
               expect=201, timeout=60)
    assert isinstance(data["id"], str)


def test_agent_ingest_batch(server, embeddings):
    data = _ok(server, "POST", "/api/agent/ingest/batch",
               {"observations": [{"content": _uniq("obs a")},
                                 {"content": _uniq("obs b")}]},
               expect=201, timeout=60)
    assert isinstance(data["ids"], list) and len(data["ids"]) == 2


def test_agent_context(server, embeddings):
    data = _ok(server, "POST", "/api/agent/context",
               {"query": "what do we know"}, timeout=60)
    for key in ("memories", "pinned", "entities", "goals", "skills",
                "retrieval_strategies", "snapshot_id"):
        assert key in data, key


def test_agent_identity(server):
    data = _ok(server, "GET", "/api/agent/identity")
    assert isinstance(data, list)


def test_agent_goals_check(server, embeddings):
    data = _ok(server, "POST", "/api/agent/goals/check",
               {"context": "working on tests"}, timeout=60)
    assert isinstance(data, list)


def test_agent_session_start_end(server, embeddings):
    started = _ok(server, "POST", "/api/agent/session/start", {}, expect=201)
    assert isinstance(started["session_id"], str)
    assert "thread_id" in started

    ended = _ok(server, "POST", "/api/agent/session/end",
                {"session_id": started["session_id"]}, timeout=60)
    assert ended == {"session_id": started["session_id"], "status": "closed"}


def test_agent_chat_requires_session_id(server):
    # DOC MISMATCH: doc marks session_id optional; code 400s without it.
    # (Validation happens before any LLM call, so this is offline-safe.)
    status, _ = _call(server, "POST", "/api/agent/chat", {"message": "hi"})
    assert status == 400


def test_agent_chat_pipeline(server):
    pytest.skip("POST /api/agent/chat runs the full pipeline against a real LLM provider")


# ══════════════════════════════════════════════════════════════
# Maintenance
# ══════════════════════════════════════════════════════════════

def test_maintenance_consolidate(server, embeddings):
    data = _ok(server, "POST", "/api/maintenance/consolidate", timeout=120)
    for key in ("short_to_mid_promoted", "mid_to_long_promoted",
                "contradictions_found", "entries_pruned", "timestamp"):
        assert key in data, key


def test_maintenance_sleep_cycle(server, embeddings):
    data = _ok(server, "POST", "/api/maintenance/sleep-cycle", timeout=120)
    assert isinstance(data, dict)
    assert "consolidation" in data


def test_maintenance_integrity_check(server):
    data = _ok(server, "POST", "/api/maintenance/integrity-check", timeout=60)
    assert isinstance(data, dict)


def test_maintenance_ann(server):
    status_data = _ok(server, "GET", "/api/maintenance/ann-status")
    assert isinstance(status_data["available"], bool)
    assert isinstance(status_data["tables"], list)

    status, env = _call(server, "POST", "/api/maintenance/ann-rebuild", timeout=120)
    if status_data["available"]:
        assert status == 200
        assert isinstance(env["data"], dict)
    else:
        assert status == 400  # hnswlib not installed


def test_maintenance_cache_clear(server):
    data = _ok(server, "POST", "/api/maintenance/cache-clear")
    assert isinstance(data["cleared"], int)


def test_maintenance_git_sync(server):
    # knowledge_git_repo is unset on a fresh DB — module returns an
    # error-shaped result rather than failing the request.
    data = _ok(server, "POST", "/api/maintenance/git-sync", timeout=60)
    assert isinstance(data, dict)


# ══════════════════════════════════════════════════════════════
# DB console
# ══════════════════════════════════════════════════════════════

def test_db_query_console(server):
    marker_sql = f"SELECT key FROM meta_config LIMIT 3 -- {uuid.uuid4().hex[:8]}"
    data = _ok(server, "POST", "/api/db/query", {"sql": marker_sql})
    assert data["columns"] == ["key"]
    assert isinstance(data["rows"], list)
    assert data["row_count"] == len(data["rows"])

    status, _ = _call(server, "POST", "/api/db/query",
                      {"sql": "DROP TABLE meta_config"})
    assert status == 403  # DROP always forbidden

    status, _ = _call(server, "POST", "/api/db/query",
                      {"sql": "INSERT INTO tags (id, name) VALUES ('x', 'y')"})
    assert status == 403  # writes need db_console_write_enabled=true

    status, _ = _call(server, "POST", "/api/db/query", {"sql": "SELECT * FROM no_such_table"})
    assert status == 400


def test_db_ai_query(server):
    status, _ = _call(server, "POST", "/api/db/ai-query", {})
    assert status == 400  # question required — checked before any LLM call
    pytest.skip("POST /api/db/ai-query with a question makes a real LLM call")


def test_db_query_schema_and_history(server):
    schema = _ok(server, "GET", "/api/db-query/schema")
    assert isinstance(schema, list)
    assert all("name" in t and "sql" in t for t in schema)
    assert any(t["name"] == "meta_config" for t in schema)

    # Run a query so history has at least one entry, then clear.
    _ok(server, "POST", "/api/db/query", {"sql": "SELECT 1 AS one"})
    history = _ok(server, "GET", "/api/db-query/history")
    assert isinstance(history, list) and len(history) >= 1
    assert all("sql" in h and "ts" in h for h in history)

    data = _ok(server, "DELETE", "/api/db-query/history")
    assert data == {"cleared": True}


# ══════════════════════════════════════════════════════════════
# Threads (undocumented CRUD)
# ══════════════════════════════════════════════════════════════

def test_thread_lifecycle(server):
    name = _uniq("thread")
    created = _ok(server, "POST", "/api/threads", {"name": name}, expect=201)
    thread_id = created["id"]

    listed = _ok(server, "GET", "/api/threads")
    assert any(t["id"] == thread_id for t in listed)

    detail = _ok(server, "GET", f"/api/threads/{thread_id}")
    assert detail["name"] == name

    updated = _ok(server, "PUT", f"/api/threads/{thread_id}", {"name": name + "2"})
    assert updated == {"id": thread_id, "updated": True}

    messages = _ok(server, "GET", f"/api/threads/{thread_id}/messages")
    assert messages == []

    deleted = _ok(server, "DELETE", f"/api/threads/{thread_id}")
    assert deleted == {"deleted": thread_id}

    status, _ = _call(server, "GET", f"/api/threads/{thread_id}")
    assert status == 404


# ══════════════════════════════════════════════════════════════
# Agent registry (undocumented)
# ══════════════════════════════════════════════════════════════

def test_agent_registry(server):
    listed = _ok(server, "GET", "/api/agents")
    assert any(a["id"] == "default" for a in listed)  # seeded at bootstrap

    agent_id = _uniq("agent")
    created = _ok(server, "POST", "/api/agents",
                  {"id": agent_id, "name": "Test Agent"}, expect=201)
    assert created["id"] == agent_id

    detail = _ok(server, "GET", f"/api/agents/{agent_id}")
    assert detail["id"] == agent_id

    updated = _ok(server, "PUT", f"/api/agents/{agent_id}",
                  {"description": "updated"})
    assert updated["id"] == agent_id

    # Rotate on the NEW agent, not 'default' — per-agent keys are additive
    # (global agent_api_key stays '' = open), so this can't lock the session.
    rotated = _ok(server, "POST", f"/api/agents/{agent_id}/rotate-key")
    assert rotated["agent_id"] == agent_id
    assert isinstance(rotated["api_key"], str) and len(rotated["api_key"]) > 20
    assert "note" in rotated


# ══════════════════════════════════════════════════════════════
# Undocumented operator remainder — smoke the simple GETs so a route or
# envelope regression anywhere in the surface still gets caught.
# ══════════════════════════════════════════════════════════════

@pytest.mark.parametrize("path", [
    "/api/contradictions",
    "/api/audit",
    "/api/views",
    "/api/attachments",
    "/api/mcp/status",
    "/api/git-sync/status",
    "/api/idle/status",
    "/api/import/status",
    "/api/markdown/watcher/status",
])
def test_misc_operator_gets(server, path):
    status, env = _call(server, "GET", path)
    assert status == 200, f"{path} -> {status}: {env['error']}"
    assert env["data"] is not None
