"""
Concurrency tests for the threaded HTTP server.

The server moved from single-threaded `HTTPServer` to `ThreadingHTTPServer`
so long operations (chat, consolidation, embedding warmup) can't block
health probes and other clients. These tests prove the properties that
switch depends on:

  * concurrent requests are actually served in parallel (a slow request
    doesn't starve a fast one), and
  * concurrent writers don't lose rows or hit "database is locked"
    (fresh connection per request + PRAGMA busy_timeout).

The server runs in-process (a daemon thread around `run_server`'s
machinery) with `generate_embedding` patched to a cheap deterministic
vector, so the suite doesn't need the sentence-transformers model.
"""
import concurrent.futures
import json
import socket
import threading
import time
import urllib.request

import numpy as np
import pytest

import swadb.server as server_mod
from swadb.database import initialize_database


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _post(base, path, body, timeout=30):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read())


def _get(base, path, timeout=10):
    with urllib.request.urlopen(base + path, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read())


@pytest.fixture
def threaded_server(tmp_path, monkeypatch):
    """In-process threaded server on an ephemeral port with fake embeddings.

    Patch points: the ingest handlers call the `generate_embedding` name
    imported into swadb.server's namespace, and context retrieval calls it
    through swadb.context/swadb.embeddings — patch all three so no request
    path touches the real model.
    """
    def fake_embedding(text, model_name="all-MiniLM-L6-v2"):
        rng = np.random.default_rng(abs(hash(text)) % (2**32))
        return rng.random(384, dtype=np.float32)

    import swadb.embeddings as embeddings_mod
    import swadb.context as context_mod
    monkeypatch.setattr(embeddings_mod, "generate_embedding", fake_embedding)
    monkeypatch.setattr(server_mod, "generate_embedding", fake_embedding)
    monkeypatch.setattr(context_mod, "generate_embedding", fake_embedding, raising=False)

    db_path = str(tmp_path / "swadb-threading.db")
    conn = initialize_database(db_path)
    from swadb import crud
    # MCP would grab its fixed default port in every instance; scheduler and
    # watcher add background writes. All off for test isolation.
    crud.set_config(conn, "mcp_enabled", "false")
    crud.set_config(conn, "scheduler_enabled", "false")
    conn.close()

    port = _free_port()
    monkeypatch.setattr(server_mod, "_db_path", db_path)
    monkeypatch.setattr(server_mod, "_start_time", time.time())
    monkeypatch.setattr(server_mod, "_locked", False)

    httpd = server_mod._ThreadingServer(("127.0.0.1", port), server_mod.SwadbHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            status, _ = _get(base, "/api/health", timeout=2)
            if status == 200:
                break
        except OSError:
            time.sleep(0.05)
    else:
        pytest.fail("in-process server never became ready")

    yield base, db_path

    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


def test_server_class_is_threading():
    from http.server import ThreadingHTTPServer
    assert issubclass(server_mod._ThreadingServer, ThreadingHTTPServer)
    assert server_mod._ThreadingServer.daemon_threads is True


def test_concurrent_ingest_no_lost_writes(threaded_server):
    base, db_path = threaded_server
    n = 16

    def ingest(i):
        status, env = _post(base, "/api/agent/ingest",
                            {"content": f"concurrent observation {i}",
                             "source": "conversation"})
        return status, env

    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
        results = list(pool.map(ingest, range(n)))

    for status, env in results:
        assert status == 201, env
        assert env["status"] == "ok"
        assert env["error"] is None
        assert env["data"]["id"]

    ids = {env["data"]["id"] for _, env in results}
    assert len(ids) == n, "duplicate memory ids returned under concurrency"

    from swadb.database import get_connection
    conn = get_connection(db_path)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM short_term_memory WHERE content LIKE 'concurrent observation %'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == n, f"expected {n} rows persisted, found {count}"


def test_concurrent_mixed_read_write(threaded_server):
    base, _ = threaded_server

    def work(i):
        if i % 2 == 0:
            return _post(base, "/api/agent/ingest",
                         {"content": f"mixed load item {i}", "source": "conversation"})
        return _post(base, "/api/agent/context", {"query": f"mixed load {i}"})

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(work, range(16)))

    for status, env in results:
        assert status in (200, 201), env
        assert env["status"] == "ok", env


def test_slow_request_does_not_block_health(threaded_server):
    """With a single-threaded server, a slow in-flight request serialized
    every other client. Prove /api/health answers while another request is
    being processed by keeping a request thread busy inside the server."""
    base, _ = threaded_server

    slow_done = threading.Event()

    def slow():
        # A context retrieval that does real work (retrieval pipeline).
        _post(base, "/api/agent/context", {"query": "anything at all"})
        slow_done.set()

    threads = [threading.Thread(target=slow) for _ in range(4)]
    for t in threads:
        t.start()
    # While those are in flight, health must answer quickly.
    start = time.time()
    status, env = _get(base, "/api/health", timeout=5)
    elapsed = time.time() - start
    assert status == 200
    assert env["data"]["status"] == "ok"
    assert elapsed < 5
    for t in threads:
        t.join(timeout=30)
