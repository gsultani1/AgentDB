"""
Webhook delivery: priority threshold, retry semantics, sleep-cycle
integration.
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from swadb import crud
from swadb import notifications


class _MockHandler(BaseHTTPRequestHandler):
    """Captures POST bodies for assertion. Class-level so tests can read."""
    received = []
    healthy = True

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b""
        try:
            type(self).received.append(json.loads(body.decode("utf-8")))
        except Exception:
            pass
        if type(self).healthy:
            self.send_response(200)
        else:
            self.send_response(500)
        self.end_headers()

    def log_message(self, *a, **k):
        pass


@pytest.fixture
def mock_webhook():
    """Per-test HTTP server. Bound to localhost:random."""
    # Reset class state for isolation
    _MockHandler.received = []
    _MockHandler.healthy = True
    server = HTTPServer(("127.0.0.1", 0), _MockHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield {"url": f"http://127.0.0.1:{port}/hook",
           "received": _MockHandler.received,
           "set_healthy": lambda v: setattr(_MockHandler, "healthy", v)}
    server.shutdown()


class TestWebhookDelivery:
    def test_threshold_filters_low_priority(self, fresh_db, mock_webhook):
        crud.set_config(fresh_db, "notification_webhook_url", mock_webhook["url"])
        crud.set_config(fresh_db, "notification_priority_threshold", "medium")

        crud.create_notification(fresh_db, "low ping", "alert_condition", priority="low")
        crud.create_notification(fresh_db, "med ping", "goal_match", priority="medium")
        crud.create_notification(fresh_db, "high ping", "contradiction_detected", priority="high")

        result = notifications.deliver_pending(fresh_db)
        time.sleep(0.05)

        assert result["attempted"] == 2  # medium + high
        assert result["delivered"] == 2
        assert result["skipped_threshold"] == 1
        titles = {p["title"] for p in mock_webhook["received"]}
        assert "low ping" not in titles
        assert "med ping" in titles
        assert "high ping" in titles

    def test_idempotent_redelivery(self, fresh_db, mock_webhook):
        crud.set_config(fresh_db, "notification_webhook_url", mock_webhook["url"])
        crud.create_notification(fresh_db, "ping", "alert_condition", priority="high")
        notifications.deliver_pending(fresh_db)
        # Second pass — already delivered, no attempts
        result = notifications.deliver_pending(fresh_db)
        assert result["attempted"] == 0

    def test_failure_then_recover(self, fresh_db, mock_webhook):
        crud.set_config(fresh_db, "notification_webhook_url", mock_webhook["url"])
        nid = crud.create_notification(fresh_db, "retryable",
                                        "alert_condition", priority="high")

        mock_webhook["set_healthy"](False)
        r1 = notifications.deliver_pending(fresh_db)
        assert r1["failed"] == 1
        assert r1["delivered"] == 0

        # Confirm row is still undelivered (eligible for retry)
        row = crud.get_notification(fresh_db, nid)
        assert not row["delivered"]

        # Server recovers
        mock_webhook["set_healthy"](True)
        r2 = notifications.deliver_pending(fresh_db)
        assert r2["delivered"] == 1
