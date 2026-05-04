"""
Workspace lifecycle: create, scan (idempotent), file-count projection, delete.
"""
import os
import time
import pytest

from swadb import crud
from swadb.workspace_scanner import scan_workspace


@pytest.fixture
def workspace_files(tmp_path):
    """A small workspace with a mix of file types."""
    root = tmp_path / "ws"
    root.mkdir()
    (root / "main.py").write_text("def hello(): pass\n")
    (root / "README.md").write_text("# title\n")
    (root / "config.json").write_text("{}\n")
    sub = root / "subdir"
    sub.mkdir()
    (sub / "more.py").write_text("x = 1\n")
    return str(root)


class TestWorkspaceLifecycle:
    def test_create_scan_rescan_delete(self, fresh_db, workspace_files):
        wid = crud.create_workspace(
            fresh_db, name="test-ws", root_path=workspace_files,
            workspace_type="codebase",
        )
        assert wid

        r1 = scan_workspace(fresh_db, wid)
        assert r1["status"] == "ok"
        assert r1["files_added"] == 4
        assert r1["files_updated"] == 0

        # Idempotent re-scan
        r2 = scan_workspace(fresh_db, wid)
        assert r2["files_added"] == 0
        assert r2["files_unchanged"] == 4

        # Delete cascades workspace_files
        fresh_db.execute("DELETE FROM workspace_files WHERE workspace_id = ?", (wid,))
        crud.delete_workspace(fresh_db, wid)
        n = fresh_db.execute("SELECT COUNT(*) FROM workspace_files").fetchone()[0]
        assert n == 0

    def test_modified_file_flips_to_updated(self, fresh_db, workspace_files):
        wid = crud.create_workspace(
            fresh_db, name="test-ws", root_path=workspace_files,
            workspace_type="codebase",
        )
        scan_workspace(fresh_db, wid)
        # Touch a file so its content_hash changes
        target = os.path.join(workspace_files, "main.py")
        original = open(target, "rb").read()
        try:
            open(target, "ab").write(b"\n# touched\n")
            time.sleep(0.05)
            r = scan_workspace(fresh_db, wid)
            assert r["files_updated"] >= 1
        finally:
            open(target, "wb").write(original)

    def test_file_count_projection_matches_api(self, fresh_db, workspace_files):
        """Mirrors what /api/workspaces does: GROUP BY workspace_id, file_type."""
        wid = crud.create_workspace(
            fresh_db, name="test-ws", root_path=workspace_files,
            workspace_type="codebase",
        )
        scan_workspace(fresh_db, wid)

        rows = fresh_db.execute(
            "SELECT file_type, COUNT(*) AS n FROM workspace_files "
            "WHERE workspace_id = ? GROUP BY file_type",
            (wid,),
        ).fetchall()
        counts = {r["file_type"]: r["n"] for r in rows}
        # 2 .py + 1 .md + 1 .json
        assert counts.get("python", 0) == 2
        assert counts.get("markdown", 0) == 1
        assert counts.get("config", 0) == 1
