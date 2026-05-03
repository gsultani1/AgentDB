"""
Webhook delivery for AgentDB notifications.

Reads `notification_webhook_url` and `notification_priority_threshold` from
meta_config. Posts undelivered notifications meeting the threshold as JSON
to the configured URL. On HTTP 2xx, marks the notification as delivered;
on failure, leaves delivered=0 for retry on the next sleep cycle.

Delivery from the sleep cycle is fire-and-forget so a slow webhook cannot
stall consolidation. Manual delivery (e.g. via /api/notifications/{id}/deliver)
is synchronous so the caller can surface the result.
"""

import json
import logging
import threading
import urllib.error
import urllib.request
from typing import Optional

from swadb import crud

logger = logging.getLogger("swadb.notifications")

_PRIORITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
_DEFAULT_TIMEOUT = 10.0


def _meets_threshold(priority: str, threshold: str) -> bool:
    return _PRIORITY_RANK.get(priority, 0) >= _PRIORITY_RANK.get(threshold, 1)


def _build_payload(notif: dict) -> dict:
    """Project a notification row into the webhook JSON payload."""
    related = notif.get("related_ids")
    if isinstance(related, str):
        try:
            related = json.loads(related)
        except (ValueError, TypeError):
            pass
    return {
        "id": notif.get("id"),
        "agent_id": notif.get("agent_id"),
        "trigger_type": notif.get("trigger_type"),
        "title": notif.get("title"),
        "body": notif.get("body"),
        "priority": notif.get("priority"),
        "related_ids": related,
        "created_at": notif.get("created_at"),
    }


def _post_webhook(url: str, payload: dict, timeout: float = _DEFAULT_TIMEOUT) -> bool:
    """POST JSON to the webhook. Return True on HTTP 2xx, False otherwise."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "swadb-webhook/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        logger.warning("Webhook POST %s returned HTTP %s", url, e.code)
        return False
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        logger.warning("Webhook POST %s failed: %s", url, e)
        return False


def deliver_notification(conn, nid: str, config: Optional[dict] = None) -> bool:
    """
    Deliver a single notification synchronously.

    Returns True if delivery succeeded (or was skipped because already delivered
    / below threshold / no webhook configured), False on attempted-but-failed
    delivery so the caller can surface a retryable error.
    """
    cfg = config or _load_config(conn)
    url = (cfg.get("notification_webhook_url") or "").strip()
    if not url:
        return True  # nothing to do; not an error

    notif = crud.get_notification(conn, nid)
    if not notif:
        return True
    if notif.get("delivered"):
        return True

    threshold = cfg.get("notification_priority_threshold", "medium")
    if not _meets_threshold(notif.get("priority", "medium"), threshold):
        return True

    payload = _build_payload(notif)
    if _post_webhook(url, payload):
        crud.mark_notification_delivered(conn, nid)
        return True
    return False


def deliver_pending(conn, config: Optional[dict] = None, limit: int = 100) -> dict:
    """
    Deliver all undelivered notifications meeting the priority threshold.
    Called from the sleep cycle. Returns counts.
    """
    cfg = config or _load_config(conn)
    url = (cfg.get("notification_webhook_url") or "").strip()
    if not url:
        return {"attempted": 0, "delivered": 0, "failed": 0, "skipped_threshold": 0}

    threshold = cfg.get("notification_priority_threshold", "medium")
    rows = crud.list_notifications(conn, limit=limit)
    pending = [n for n in rows if not n.get("delivered")]

    attempted = 0
    delivered = 0
    failed = 0
    skipped = 0

    for notif in pending:
        if not _meets_threshold(notif.get("priority", "medium"), threshold):
            skipped += 1
            continue
        attempted += 1
        if _post_webhook(url, _build_payload(notif)):
            crud.mark_notification_delivered(conn, notif["id"])
            delivered += 1
        else:
            failed += 1

    return {
        "attempted": attempted,
        "delivered": delivered,
        "failed": failed,
        "skipped_threshold": skipped,
    }


def deliver_async(conn_factory, nid: str) -> None:
    """
    Fire-and-forget delivery from a daemon thread. Used by callers that
    must not block on webhook latency (e.g. the sleep cycle, or any path
    creating a notification mid-request).

    `conn_factory` is a callable returning a fresh sqlite3.Connection so
    the worker thread does not share the caller's connection object.
    """
    def _worker():
        try:
            conn = conn_factory()
            try:
                deliver_notification(conn, nid)
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Async webhook delivery failed for %s: %s", nid, e)

    t = threading.Thread(target=_worker, daemon=True, name=f"swadb-webhook-{nid[:8]}")
    t.start()


def _load_config(conn) -> dict:
    """Load only the config keys this module needs."""
    out = {}
    for key in ("notification_webhook_url", "notification_priority_threshold"):
        val = crud.get_config_value(conn, key)
        if val is not None:
            out[key] = val
    return out
