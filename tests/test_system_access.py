"""
File r/w/list/stat + shell exec — the security boundaries that gate
agent access to the host filesystem.

The realpath-then-commonpath pattern is what makes grants safe against
symlink escape and substring-prefix neighbors. These tests pin both.
"""
import os
import pytest
import sqlite3 as _sq

from swadb import crud
from swadb.system_access import (
    AccessDenied, resolve_safe_path,
    read_file, write_file, list_dir, stat_path,
    execute_shell,
)


@pytest.fixture
def sandbox(fresh_db, tmp_path):
    """A 'sandbox' dir + an 'outside' dir, with one file in each."""
    sb = tmp_path / "sandbox"
    out = tmp_path / "outside"
    sb.mkdir()
    out.mkdir()
    (sb / "data.txt").write_text("inside content")
    (out / "secret.txt").write_text("OUTSIDE SECRET")
    # Confusingly-named neighbor — exercises the substring-prefix bug
    neighbor = tmp_path / "sandbox_evil"
    neighbor.mkdir()
    (neighbor / "x.txt").write_text("not allowed")
    return {"db": fresh_db, "sandbox": str(sb), "outside": str(out),
            "neighbor": str(neighbor), "tmp": tmp_path}


class TestPathBoundaries:
    def test_no_grants_denies_everything(self, sandbox):
        with pytest.raises(AccessDenied):
            read_file(sandbox["db"], "default", os.path.join(sandbox["sandbox"], "data.txt"))
        with pytest.raises(AccessDenied):
            list_dir(sandbox["db"], "default", sandbox["sandbox"])
        with pytest.raises(AccessDenied):
            stat_path(sandbox["db"], "default", os.path.join(sandbox["sandbox"], "data.txt"))

    def test_read_grant_allows_inside_denies_outside(self, sandbox):
        crud.create_file_access_grant(
            sandbox["db"], directory_path=sandbox["sandbox"],
            agent_id="default", permission="read",
        )
        # Inside grant works
        result = read_file(sandbox["db"], "default", os.path.join(sandbox["sandbox"], "data.txt"))
        assert result["content"] == "inside content"
        # Outside grant blocked
        with pytest.raises(AccessDenied):
            read_file(sandbox["db"], "default", os.path.join(sandbox["outside"], "secret.txt"))

    def test_substring_prefix_neighbor_rejected(self, sandbox):
        """`/sandbox` grant must NOT cover `/sandbox_evil` — the
        startswith() footgun this fixes."""
        crud.create_file_access_grant(
            sandbox["db"], directory_path=sandbox["sandbox"],
            agent_id="default", permission="read",
        )
        with pytest.raises(AccessDenied):
            read_file(sandbox["db"], "default",
                      os.path.join(sandbox["neighbor"], "x.txt"))

    def test_read_grant_blocks_writes(self, sandbox):
        crud.create_file_access_grant(
            sandbox["db"], directory_path=sandbox["sandbox"],
            agent_id="default", permission="read",
        )
        with pytest.raises(AccessDenied):
            write_file(sandbox["db"], "default",
                       os.path.join(sandbox["sandbox"], "new.txt"), "x")

    def test_read_write_grant_allows_writes(self, sandbox):
        crud.create_file_access_grant(
            sandbox["db"], directory_path=sandbox["sandbox"],
            agent_id="default", permission="read_write",
        )
        target = os.path.join(sandbox["sandbox"], "new.txt")
        result = write_file(sandbox["db"], "default", target, "hello")
        assert result["bytes_written"] == 5
        assert read_file(sandbox["db"], "default", target)["content"] == "hello"

    @pytest.mark.skipif(os.name == "nt",
                       reason="Windows symlinks need admin/dev mode; trust the realpath logic on POSIX")
    def test_symlink_escape_denied(self, sandbox):
        crud.create_file_access_grant(
            sandbox["db"], directory_path=sandbox["sandbox"],
            agent_id="default", permission="read",
        )
        escape = os.path.join(sandbox["sandbox"], "escape")
        os.symlink(os.path.join(sandbox["outside"], "secret.txt"), escape)
        with pytest.raises(AccessDenied):
            read_file(sandbox["db"], "default", escape)


class TestListAndStat:
    def test_list_dir_returns_entries(self, sandbox):
        crud.create_file_access_grant(
            sandbox["db"], directory_path=sandbox["sandbox"],
            agent_id="default", permission="read",
        )
        result = list_dir(sandbox["db"], "default", sandbox["sandbox"])
        names = sorted(e["name"] for e in result["entries"])
        assert "data.txt" in names

    def test_stat_returns_metadata(self, sandbox):
        crud.create_file_access_grant(
            sandbox["db"], directory_path=sandbox["sandbox"],
            agent_id="default", permission="read",
        )
        result = stat_path(sandbox["db"], "default",
                           os.path.join(sandbox["sandbox"], "data.txt"))
        assert result["is_file"] is True
        assert result["size_bytes"] == 14  # len("inside content")


class TestShellExecution:
    def test_shell_disabled_by_default(self, sandbox):
        with pytest.raises(AccessDenied, match="disabled"):
            execute_shell(sandbox["db"], "default", "echo hi")

    def test_shell_runs_when_enabled_with_grant(self, sandbox):
        crud.set_config(sandbox["db"], "shell_access_enabled", "true")
        crud.create_file_access_grant(
            sandbox["db"], directory_path=sandbox["sandbox"],
            agent_id="default", permission="read_write",
        )
        result = execute_shell(sandbox["db"], "default",
                               "echo hello-from-swadb",
                               working_dir=sandbox["sandbox"])
        assert result["exit_code"] == 0
        assert "hello-from-swadb" in result["stdout"]

    def test_denied_keyword_rejected_before_subprocess(self, sandbox):
        crud.set_config(sandbox["db"], "shell_access_enabled", "true")
        crud.create_file_access_grant(
            sandbox["db"], directory_path=sandbox["sandbox"],
            agent_id="default", permission="read_write",
        )
        with pytest.raises(AccessDenied, match="denied keyword"):
            execute_shell(sandbox["db"], "default",
                          "rm -rf / ; echo gotcha",
                          working_dir=sandbox["sandbox"])

    def test_working_dir_outside_grant_rejected(self, sandbox):
        crud.set_config(sandbox["db"], "shell_access_enabled", "true")
        crud.create_file_access_grant(
            sandbox["db"], directory_path=sandbox["sandbox"],
            agent_id="default", permission="read_write",
        )
        with pytest.raises(AccessDenied):
            execute_shell(sandbox["db"], "default", "echo x",
                          working_dir=sandbox["outside"])
