"""
Scheduled task execution for AgentDB.

Provides:
- runtime schema bootstrap for scheduled_tasks
- interval-based task execution
- a background runner that executes due tasks
"""

import os
import threading
from datetime import datetime, timedelta

from agentdb import crud
from agentdb.consolidation import run_consolidation_cycle
from agentdb.database import get_connection
from agentdb.schema import CREATE_INDEXES, CREATE_SCHEDULED_TASKS
from agentdb.sleep import run_sleep_cycle


def _now():
    return datetime.utcnow()


def _now_iso():
    return _now().isoformat()


def compute_next_run(interval_seconds, from_time=None):
    """Compute the next run timestamp for an interval task."""
    base = from_time or _now()
    if isinstance(base, str):
        base = datetime.fromisoformat(base)
    return (base + timedelta(seconds=int(interval_seconds))).isoformat()


def ensure_scheduler_schema(conn):
    """Ensure the scheduler table and indexes exist for upgraded databases."""
    conn.executescript(CREATE_SCHEDULED_TASKS)
    for idx in CREATE_INDEXES:
        if "scheduled_tasks" in idx:
            conn.execute(idx)
    conn.commit()


def run_integrity_check(conn):
    """Scan polymorphic reference columns for orphaned IDs."""
    from agentdb.schema import CONTENT_TABLES

    orphans_found = 0
    orphans_detail = []

    for poly_table in ("relations", "tag_assignments", "feedback"):
        if poly_table == "relations":
            id_cols = [("source_id", "source_table"), ("target_id", "target_table")]
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
                if exists:
                    continue
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
                    conn,
                    poly_table,
                    row["id"],
                    "delete" if orphan_mode == "auto" else "update",
                    "manual",
                    after_snapshot={"orphan_detected": True, "references": f"{ref_table}.{ref_id}"},
                )
    conn.commit()
    return {
        "orphans_found": orphans_found,
        "orphans": orphans_detail[:50],
        "action": crud.get_config_value(conn, "orphan_handling_mode", "flag"),
    }


def run_workspace_scan(conn):
    """Walk known workspaces and report how many files were seen."""
    workspaces = crud.list_workspaces(conn)
    scanned = 0
    checked = 0
    for ws in workspaces:
        root = ws.get("root_path") or ws.get("path", "")
        if root and os.path.isdir(root):
            checked += 1
            for _, _, files in os.walk(root):
                scanned += len(files)
    return {
        "workspaces_checked": checked,
        "files_found": scanned,
    }


def _task_payload(task):
    payload = task.get("payload_json")
    return payload if isinstance(payload, dict) else {}


def execute_scheduled_task(conn, task):
    """Execute a single scheduled task and return its result."""
    action = task["action_type"]
    payload = _task_payload(task)

    if action == "notify":
        title = payload.get("title") or task["name"]
        body = payload.get("body") or task.get("description") or "Scheduled task fired."
        priority = payload.get("priority", "medium")
        notification_id = crud.create_notification(
            conn,
            title=title,
            trigger_type="alert_condition",
            agent_id=task.get("agent_id", "default"),
            body=body,
            priority=priority,
            related_ids={"scheduled_task_id": task["id"]},
        )
        return {
            "action": "notify",
            "notification_id": notification_id,
            "title": title,
        }

    if action == "consolidate":
        return run_consolidation_cycle(conn)

    if action == "sleep_cycle":
        return run_sleep_cycle(conn)

    if action == "workspace_scan":
        return run_workspace_scan(conn)

    if action == "integrity_check":
        return run_integrity_check(conn)

    raise ValueError(f"Unsupported scheduled task action: {action}")


def run_scheduled_task_now(conn, task_id):
    """Execute a scheduled task immediately and persist its run state."""
    task = crud.get_scheduled_task(conn, task_id)
    if not task:
        raise ValueError(f"Scheduled task not found: {task_id}")

    last_run_at = _now_iso()
    try:
        result = execute_scheduled_task(conn, task)
        if task.get("status") == "paused":
            next_run_at = task["next_run_at"]
            status = "paused"
        else:
            next_run_at = compute_next_run(task["interval_seconds"], last_run_at)
            status = "active"
        crud.record_scheduled_task_success(
            conn, task_id, last_run_at, next_run_at, result=result, status=status
        )
        return {"task_id": task_id, "status": "ok", "result": result, "next_run_at": next_run_at}
    except Exception as exc:
        crud.record_scheduled_task_failure(conn, task_id, last_run_at, exc, status="error")
        crud.create_notification(
            conn,
            title=f"Scheduled task failed: {task['name']}",
            trigger_type="alert_condition",
            agent_id=task.get("agent_id", "default"),
            body=str(exc),
            priority="high",
            related_ids={"scheduled_task_id": task_id},
        )
        raise


class ScheduledTaskRunner:
    """Background runner that polls and executes due scheduled tasks."""

    def __init__(self, db_path):
        self._db_path = db_path
        self._thread = None
        self._stop_event = threading.Event()
        self._last_result = None

    @property
    def last_result(self):
        return self._last_result

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)

    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                conn = get_connection(self._db_path)
                ensure_scheduler_schema(conn)
                if crud.get_config_value(conn, "scheduler_enabled", "true") != "true":
                    conn.close()
                    self._stop_event.wait(60)
                    continue

                poll_interval = int(
                    crud.get_config_value(conn, "scheduler_poll_interval_seconds", "5")
                )
                due_tasks = crud.list_due_scheduled_tasks(conn, limit=20)
                for task in due_tasks:
                    last_run_at = _now_iso()
                    try:
                        result = execute_scheduled_task(conn, task)
                        next_run_at = compute_next_run(task["interval_seconds"], last_run_at)
                        crud.record_scheduled_task_success(
                            conn,
                            task["id"],
                            last_run_at,
                            next_run_at,
                            result=result,
                            status="active",
                        )
                        self._last_result = {
                            "task_id": task["id"],
                            "task_name": task["name"],
                            "ran_at": last_run_at,
                            "result": result,
                        }
                    except Exception as exc:
                        crud.record_scheduled_task_failure(
                            conn, task["id"], last_run_at, exc, status="error"
                        )
                        crud.create_notification(
                            conn,
                            title=f"Scheduled task failed: {task['name']}",
                            trigger_type="alert_condition",
                            agent_id=task.get("agent_id", "default"),
                            body=str(exc),
                            priority="high",
                            related_ids={"scheduled_task_id": task["id"]},
                        )
                        self._last_result = {
                            "task_id": task["id"],
                            "task_name": task["name"],
                            "ran_at": last_run_at,
                            "error": str(exc),
                        }
                conn.close()
                if self._stop_event.wait(max(poll_interval, 1)):
                    break
            except Exception as exc:
                self._last_result = {"error": str(exc), "ran_at": _now_iso()}
                self._stop_event.wait(30)
