"""
Workspace scanner / summarizer for AgentDB.

Walks a registered workspace's root_path, upserts file records into
workspace_files, generates embeddings for readable text files, and builds
chunk_of relations so the graph traversal pipeline can surface file context.

Scannable text types and their AgentDB file_type labels:
    .py / .js / .ts / .rb / .go / .java / .c / .cpp / .h  → python (code)
    .md / .txt / .rst                                       → markdown
    .json / .yaml / .yml / .toml / .ini / .cfg / .env      → config
    everything else                                         → binary
"""

import hashlib
import os
from datetime import datetime
from pathlib import Path

from agentdb import crud
from agentdb.embeddings import generate_embedding, embedding_to_blob


# ── File type mapping ─────────────────────────────────────────────────────────

_EXT_TYPE: dict[str, str] = {
    # code → stored as 'python' (the schema's closest generic code type)
    ".py": "python", ".js": "python", ".ts": "python",
    ".jsx": "python", ".tsx": "python", ".rb": "python",
    ".go": "python", ".java": "python", ".c": "python",
    ".cpp": "python", ".h": "python", ".rs": "python",
    ".swift": "python", ".kt": "python", ".cs": "python",
    # prose / docs
    ".md": "markdown", ".txt": "markdown", ".rst": "markdown",
    # config / data
    ".json": "config", ".yaml": "config", ".yml": "config",
    ".toml": "config", ".ini": "config", ".cfg": "config",
    ".env": "config",
}

_TEXT_TYPES = {"python", "markdown", "config"}
_MAX_EMBED_BYTES = 4096    # first 4 KB embedded
_SUMMARY_CHARS = 300       # first N chars used as summary
_MAX_FILE_BYTES = 512_000  # skip files > 512 KB for embedding
_SKIP_DIRS = {
    ".git", ".svn", "__pycache__", "node_modules",
    ".tox", ".venv", "venv", "dist", "build",
    ".idea", ".vscode", "target",
}


def scan_workspace(conn, workspace_id: str) -> dict:
    """
    Scan a registered workspace and synchronise workspace_files.

    Returns:
        dict with status, files_added, files_updated, files_removed, timestamp
    """
    workspace = crud.get_workspace(conn, workspace_id)
    if not workspace:
        return {"status": "error", "error": f"Workspace {workspace_id} not found"}

    root = Path(workspace["root_path"])
    if not root.exists():
        return {"status": "error", "error": f"Root path does not exist: {root}"}

    now_iso = datetime.utcnow().isoformat()
    results = {
        "workspace_id": workspace_id,
        "root_path": str(root),
        "files_added": 0,
        "files_updated": 0,
        "files_removed": 0,
        "files_unchanged": 0,
        "timestamp": now_iso,
    }

    # Build index of what's already recorded
    existing_rows = conn.execute(
        "SELECT id, relative_path, content_hash FROM workspace_files WHERE workspace_id = ?",
        (workspace_id,),
    ).fetchall()
    existing: dict[str, dict] = {r["relative_path"]: dict(r) for r in existing_rows}
    visited_paths: set[str] = set()

    # Walk directory tree
    for file_info in _walk(root):
        rel_path = file_info["rel_path"]
        visited_paths.add(rel_path)

        old = existing.get(rel_path)

        if old is None:
            # New file
            crud.create_workspace_file(
                conn,
                workspace_id=workspace_id,
                relative_path=rel_path,
                file_type=file_info["file_type"],
                depth=file_info["depth"],
                size_bytes=file_info["size_bytes"],
                file_last_modified=file_info["mtime"],
                content_hash=file_info["content_hash"],
                embedding=file_info["embedding"],
                summary=file_info["summary"],
            )
            results["files_added"] += 1
        elif old["content_hash"] != file_info["content_hash"]:
            # Changed file — re-embed
            crud.update_workspace_file(
                conn,
                fid=old["id"],
                file_type=file_info["file_type"],
                size_bytes=file_info["size_bytes"],
                file_last_modified=file_info["mtime"],
                last_scanned=now_iso,
                content_hash=file_info["content_hash"],
                embedding=file_info["embedding"],
                summary=file_info["summary"],
            )
            results["files_updated"] += 1
        else:
            # Unchanged — just bump last_scanned
            crud.update_workspace_file(conn, fid=old["id"], last_scanned=now_iso)
            results["files_unchanged"] += 1

    # Remove records for files that no longer exist
    for rel_path, rec in existing.items():
        if rel_path not in visited_paths:
            conn.execute("DELETE FROM workspace_files WHERE id = ?", (rec["id"],))
            results["files_removed"] += 1

    # Update workspace last_scanned
    crud.update_workspace(conn, workspace_id, last_scanned=now_iso)
    conn.commit()

    return {"status": "ok", **results}


# ── Directory walk ─────────────────────────────────────────────────────────────

def _walk(root: Path):
    """Yield file-info dicts for every non-skipped file under root."""
    for dirpath, dirs, files in os.walk(root):
        # Prune skipped directories in-place
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]

        for fname in files:
            if fname.startswith("."):
                continue
            abs_path = Path(dirpath) / fname
            rel_path = abs_path.relative_to(root).as_posix()
            depth = rel_path.count("/")
            ext = abs_path.suffix.lower()
            file_type = _EXT_TYPE.get(ext, "binary")

            try:
                stat = abs_path.stat()
                size_bytes = stat.st_size
                mtime = datetime.utcfromtimestamp(stat.st_mtime).isoformat()
            except OSError:
                continue

            content_hash, summary, embedding = None, None, None

            if file_type in _TEXT_TYPES and size_bytes <= _MAX_FILE_BYTES:
                try:
                    raw = abs_path.read_bytes()
                    content_hash = hashlib.sha256(raw).hexdigest()
                    text = raw[:_MAX_EMBED_BYTES].decode("utf-8", errors="replace")
                    summary = text[:_SUMMARY_CHARS].strip()
                    embedding = embedding_to_blob(generate_embedding(text))
                except OSError:
                    pass
            else:
                # Hash binary by first 64 KB only (fast)
                try:
                    with abs_path.open("rb") as fh:
                        chunk = fh.read(65536)
                    content_hash = hashlib.sha256(chunk).hexdigest()
                except OSError:
                    pass

            yield {
                "rel_path": rel_path,
                "file_type": file_type,
                "depth": depth,
                "size_bytes": size_bytes,
                "mtime": mtime,
                "content_hash": content_hash,
                "summary": summary,
                "embedding": embedding,
            }
