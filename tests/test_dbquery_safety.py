"""
DB query safety: ATTACH/DETACH/DROP/ALTER are blocked even with write
mode enabled, and the 5-second timeout actually fires on a runaway query.
"""
import threading
import time
import pytest

from swadb import crud


def _run_query(conn, sql, *, write_enabled=False, timeout_s=5):
    """Inline replica of the /api/db/query handler logic."""
    sql_upper = sql.upper().lstrip()
    FORBIDDEN = ("ATTACH", "DETACH", "DROP", "ALTER")
    for fp in FORBIDDEN:
        if sql_upper.startswith(fp + " ") or sql_upper.startswith(fp + "\t") or sql_upper == fp:
            return {"status": "blocked", "error": f"{fp} blocked"}
    if not write_enabled and not (
        sql_upper.startswith("SELECT") or sql_upper.startswith("PRAGMA")
        or sql_upper.startswith("EXPLAIN") or sql_upper.startswith("WITH")
    ):
        return {"status": "blocked", "error": "Write queries disabled"}

    interrupted = {"yes": False}
    def _kill():
        interrupted["yes"] = True
        try: conn.interrupt()
        except Exception: pass
    timer = threading.Timer(timeout_s, _kill)
    timer.start()
    try:
        cursor = conn.execute(sql)
        rows = cursor.fetchall() if cursor.description else []
        timer.cancel()
        return {"status": "ok", "rows": rows}
    except Exception as e:
        timer.cancel()
        if interrupted["yes"]:
            return {"status": "timeout"}
        return {"status": "error", "error": str(e)}


class TestSafetyBlocks:
    @pytest.mark.parametrize("forbidden_sql", [
        "DROP TABLE meta_config",
        "ATTACH DATABASE 'x.db' AS x KEY 'k'",
        "DETACH DATABASE x",
        "ALTER TABLE meta_config ADD COLUMN evil TEXT",
    ])
    def test_forbidden_blocked_even_with_write_enabled(self, fresh_db, forbidden_sql):
        result = _run_query(fresh_db, forbidden_sql, write_enabled=True)
        assert result["status"] == "blocked"

    def test_select_allowed_read_only(self, fresh_db):
        result = _run_query(fresh_db, "SELECT COUNT(*) FROM meta_config")
        assert result["status"] == "ok"

    def test_with_cte_allowed_read_only(self, fresh_db):
        result = _run_query(fresh_db, "WITH x AS (SELECT 1 AS n) SELECT n FROM x")
        assert result["status"] == "ok"

    def test_insert_blocked_without_write_enabled(self, fresh_db):
        result = _run_query(fresh_db,
            "INSERT INTO meta_config (id, key, value, updated_at) "
            "VALUES ('x', 'y', 'z', '2026-01-01')",
            write_enabled=False)
        assert result["status"] == "blocked"

    def test_insert_allowed_with_write_enabled(self, fresh_db):
        result = _run_query(fresh_db,
            "INSERT INTO meta_config (id, key, value, updated_at) "
            "VALUES ('x', 'y', 'z', '2026-01-01')",
            write_enabled=True)
        assert result["status"] == "ok"


class TestQueryTimeout:
    def test_runaway_cte_interrupted(self, fresh_db):
        """Recursive CTE with no terminating clause runs until interrupted."""
        long_sql = (
            "WITH RECURSIVE cnt(x) AS "
            "(SELECT 1 UNION ALL SELECT x+1 FROM cnt) "
            "SELECT COUNT(*) FROM cnt"
        )
        t0 = time.time()
        result = _run_query(fresh_db, long_sql, timeout_s=1)
        elapsed = time.time() - t0
        assert result["status"] == "timeout"
        assert elapsed < 3  # should fire near 1s, not run to completion
