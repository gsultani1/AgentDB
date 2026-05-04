"""
Local system access for swadb: file read/write/list/stat and shell execute,
all gated by `file_access_grants` rows and a per-feature config toggle.

Security model
──────────────
This module is *not* a sandbox. Anything that reaches it has already
authenticated as the operator. The guards are designed to:

  1. Prevent an agent or operator from accidentally reading/writing outside
     the directories explicitly granted in `file_access_grants`.
  2. Resolve symlinks before checking containment so `/grant/escape ->
     /etc/passwd` cannot bypass the grant boundary.
  3. Use `os.path.commonpath` rather than `str.startswith` for containment
     so `/srv/dat` does not accidentally cover `/srv/data`.
  4. Apply a configurable timeout to shell commands so a runaway process
     cannot hang the server thread.
  5. Reject shell commands containing operator-defined denied keywords as a
     typo backstop (not a security boundary; a determined caller can
     trivially evade with shell substitution).

Anything stronger (cgroups, seccomp, Docker, chroot) is intentionally out
of scope and would have to live at the deployment layer.
"""

import os
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from swadb import crud


# ── Path resolution + grant check ─────────────────────────────────────────────

class AccessDenied(Exception):
    """Raised when a path or command is rejected by the grant/keyword check."""


def _grants_for(conn, agent_id: str):
    grants = crud.list_file_access_grants(conn, agent_id) or []
    if agent_id != "default":
        # Always include grants for 'default' so an operator-issued grant on
        # the default agent applies to all unscoped callers.
        grants += [g for g in (crud.list_file_access_grants(conn, "default") or [])
                   if g["id"] not in {x["id"] for x in grants}]
    return grants


def resolve_safe_path(conn, agent_id: str, path: str,
                      require_write: bool = False) -> str:
    """
    Resolve `path` to a real, absolute filesystem path that is contained
    within at least one grant for `agent_id` (or the default agent).

    Raises AccessDenied if no grant covers the resolved path. Symlinks are
    followed before containment is checked so a symlink can't escape its
    grant.
    """
    if not path:
        raise AccessDenied("path is required")

    # NOTE: realpath returns a real path even when the file does not yet
    # exist (the leaf can be missing). We rely on this for write_file's
    # "create new file" case.
    real = os.path.realpath(os.path.abspath(path))

    grants = _grants_for(conn, agent_id)
    for grant in grants:
        if require_write and grant["permission"] != "read_write":
            continue
        grant_root = os.path.realpath(os.path.abspath(grant["directory_path"]))
        try:
            common = os.path.commonpath([real, grant_root])
        except ValueError:
            # Different drives on Windows, or path mismatch
            continue
        # Containment: real is grant_root or a descendant
        if common == grant_root:
            return real

    raise AccessDenied(
        f"no {'read_write' if require_write else 'read'} grant covers {path!r}"
    )


# ── File operations ───────────────────────────────────────────────────────────

# 5 MB cap on a single read/write to keep responses sane and prevent OOM.
MAX_FILE_BYTES = 5 * 1024 * 1024


def stat_path(conn, agent_id: str, path: str) -> dict:
    real = resolve_safe_path(conn, agent_id, path)
    if not os.path.exists(real):
        raise FileNotFoundError(f"path does not exist: {real}")
    st = os.stat(real)
    return {
        "path": real,
        "is_file": os.path.isfile(real),
        "is_dir": os.path.isdir(real),
        "size_bytes": st.st_size,
        "modified_at": datetime.fromtimestamp(st.st_mtime, timezone.utc).replace(tzinfo=None).isoformat(),
        "created_at": datetime.fromtimestamp(st.st_ctime, timezone.utc).replace(tzinfo=None).isoformat(),
    }


def list_dir(conn, agent_id: str, path: str, max_entries: int = 1000) -> dict:
    real = resolve_safe_path(conn, agent_id, path)
    if not os.path.isdir(real):
        raise NotADirectoryError(f"not a directory: {real}")
    entries = []
    truncated = False
    with os.scandir(real) as it:
        for i, entry in enumerate(it):
            if i >= max_entries:
                truncated = True
                break
            try:
                st = entry.stat(follow_symlinks=False)
                entries.append({
                    "name": entry.name,
                    "is_file": entry.is_file(follow_symlinks=False),
                    "is_dir": entry.is_dir(follow_symlinks=False),
                    "is_symlink": entry.is_symlink(),
                    "size_bytes": st.st_size,
                    "modified_at": datetime.fromtimestamp(st.st_mtime, timezone.utc).replace(tzinfo=None).isoformat(),
                })
            except OSError:
                # Permission errors on a single entry shouldn't fail the listing
                continue
    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
    return {"path": real, "entries": entries, "truncated": truncated}


def read_file(conn, agent_id: str, path: str,
              max_bytes: int = MAX_FILE_BYTES,
              binary: bool = False) -> dict:
    real = resolve_safe_path(conn, agent_id, path)
    if not os.path.isfile(real):
        raise FileNotFoundError(f"not a file: {real}")
    size = os.path.getsize(real)
    if size > max_bytes:
        raise ValueError(
            f"file too large: {size} bytes > {max_bytes} byte cap "
            f"(adjust max_bytes to override)"
        )
    with open(real, "rb") as f:
        raw = f.read()
    if binary:
        # Caller wants raw bytes; return a hex-encoded string so JSON survives
        return {"path": real, "size_bytes": size, "encoding": "hex",
                "content": raw.hex()}
    try:
        text = raw.decode("utf-8")
        return {"path": real, "size_bytes": size, "encoding": "utf-8",
                "content": text}
    except UnicodeDecodeError:
        return {"path": real, "size_bytes": size, "encoding": "hex",
                "content": raw.hex(),
                "warning": "file is not valid UTF-8; returned as hex"}


def write_file(conn, agent_id: str, path: str, content: str,
               encoding: str = "utf-8", append: bool = False) -> dict:
    real = resolve_safe_path(conn, agent_id, path, require_write=True)
    # Reject if write would create a file outside an existing directory inside
    # the grant. The path can resolve via realpath even when leaf is missing.
    parent = os.path.dirname(real)
    if not os.path.isdir(parent):
        raise FileNotFoundError(f"parent directory does not exist: {parent}")
    raw = content.encode(encoding)
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError(
            f"content too large: {len(raw)} bytes > {MAX_FILE_BYTES} byte cap"
        )
    mode = "ab" if append else "wb"
    with open(real, mode) as f:
        f.write(raw)
    return {"path": real, "bytes_written": len(raw), "appended": append}


# ── Shell execution ───────────────────────────────────────────────────────────

DEFAULT_DENIED_KEYWORDS = [
    "rm -rf /",
    "rm -rf ~",
    ":(){:|:&};:",     # fork bomb
    "mkfs",
    "format c:",
    "dd if=",
    "> /dev/sda",
    "shutdown",
    "reboot",
    "halt",
]


def _load_shell_config(conn) -> dict:
    return {
        "enabled": crud.get_config_value(conn, "shell_access_enabled", "false") == "true",
        "default_timeout": int(crud.get_config_value(conn, "shell_timeout_seconds", "30")),
        "max_timeout": int(crud.get_config_value(conn, "shell_max_timeout_seconds", "300")),
        "denied_keywords": _parse_denied_keywords(
            crud.get_config_value(conn, "shell_denied_keywords", "")
        ),
    }


def _parse_denied_keywords(raw: str):
    import json as _j
    if not raw:
        return list(DEFAULT_DENIED_KEYWORDS)
    try:
        parsed = _j.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except (ValueError, TypeError):
        pass
    return list(DEFAULT_DENIED_KEYWORDS)


def execute_shell(conn, agent_id: str, command: str,
                  working_dir: Optional[str] = None,
                  timeout_seconds: Optional[int] = None,
                  task_id: Optional[str] = None) -> dict:
    """
    Run `command` via shell=True after passing the deny-keyword check.
    Logs the entire lifecycle to `shell_command_log` regardless of outcome.

    Returns a dict with stdout, stderr, exit_code, duration_ms, log_id, and
    a `truncated` flag if either stream exceeded MAX_FILE_BYTES.
    """
    if not command or not command.strip():
        raise ValueError("command is required")

    cfg = _load_shell_config(conn)
    if not cfg["enabled"]:
        raise AccessDenied("shell access is disabled (shell_access_enabled=false)")

    # Deny-keyword check (case-insensitive substring on the raw command)
    cmd_lower = command.lower()
    for kw in cfg["denied_keywords"]:
        if kw and kw.lower() in cmd_lower:
            raise AccessDenied(f"command rejected: contains denied keyword {kw!r}")

    # Working directory must be inside a grant
    if working_dir:
        working_dir = resolve_safe_path(conn, agent_id, working_dir)
    else:
        working_dir = None  # use server CWD

    # Clamp timeout
    timeout = timeout_seconds or cfg["default_timeout"]
    timeout = max(1, min(int(timeout), cfg["max_timeout"]))

    # Log start
    log_id = crud.create_shell_command_log(
        conn, command=command, agent_id=agent_id,
        task_id=task_id, working_dir=working_dir,
    )

    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=working_dir,
            capture_output=True,
            timeout=timeout,
            text=True,
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        stdout = (proc.stdout or "")[:MAX_FILE_BYTES]
        stderr = (proc.stderr or "")[:MAX_FILE_BYTES]
        truncated = (
            (proc.stdout and len(proc.stdout) > MAX_FILE_BYTES) or
            (proc.stderr and len(proc.stderr) > MAX_FILE_BYTES)
        )
        crud.complete_shell_command_log(
            conn, log_id, stdout=stdout, stderr=stderr,
            exit_code=proc.returncode, duration_ms=duration_ms,
        )
        return {
            "log_id": log_id,
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "duration_ms": duration_ms,
            "truncated": bool(truncated),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as e:
        duration_ms = int((time.monotonic() - started) * 1000)
        stdout = (e.stdout or "")[:MAX_FILE_BYTES] if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", errors="replace")[:MAX_FILE_BYTES]
        stderr = (e.stderr or "")[:MAX_FILE_BYTES] if isinstance(e.stderr, str) else (e.stderr or b"").decode("utf-8", errors="replace")[:MAX_FILE_BYTES]
        crud.complete_shell_command_log(
            conn, log_id, stdout=stdout,
            stderr=(stderr + f"\n[swadb] killed after {timeout}s timeout").strip(),
            exit_code=-1, duration_ms=duration_ms,
        )
        return {
            "log_id": log_id,
            "exit_code": -1,
            "stdout": stdout,
            "stderr": stderr,
            "duration_ms": duration_ms,
            "truncated": False,
            "timed_out": True,
        }
    except Exception as e:
        duration_ms = int((time.monotonic() - started) * 1000)
        crud.complete_shell_command_log(
            conn, log_id, stdout="", stderr=str(e),
            exit_code=-2, duration_ms=duration_ms,
        )
        raise
