"""
Git knowledge sync for AgentDB v1.5.

Synchronizes a git repository of markdown files with the AgentDB database.
The repository serves as the authoring source of truth; the database is
the runtime source of truth.

Supports:
- Pull from remote (fast-forward only)
- Detect changed files since last sync
- Process through markdown pipeline
- Optional auto-commit from UI edits
"""

import os
import subprocess
from datetime import datetime

from agentdb import crud
from agentdb.markdown_parser import process_markdown_document


def sync_from_git(conn, config=None):
    """
    Pull latest changes from the configured knowledge git repo and process
    any changed markdown files through the pipeline.

    Args:
        conn: sqlite3.Connection
        config: dict with keys: knowledge_git_repo, knowledge_git_branch,
                last_git_sync_commit, last_git_sync_at

    Returns:
        dict with sync results: files_processed, records_created, errors, commit_hash
    """
    if config is None:
        config = _load_git_config(conn)

    repo_path = config.get("knowledge_git_repo", "")
    branch = config.get("knowledge_git_branch", "main")
    last_commit = config.get("last_git_sync_commit", "")

    if not repo_path or not os.path.isdir(repo_path):
        return {"error": "knowledge_git_repo not configured or directory not found",
                "files_processed": 0}

    result = {
        "files_processed": 0,
        "records_created": 0,
        "records_updated": 0,
        "errors": [],
        "commit_hash": "",
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Step 1: git pull --ff-only
    try:
        pull_result = subprocess.run(
            ["git", "-C", repo_path, "pull", "--ff-only", "origin", branch],
            capture_output=True, text=True, timeout=60,
        )
        if pull_result.returncode != 0:
            stderr = pull_result.stderr.strip()
            if "conflict" in stderr.lower():
                return {"error": f"Git conflict detected: {stderr}. "
                        "Resolve conflicts in the repository and re-trigger sync.",
                        "files_processed": 0}
            # Non-zero but not a conflict — could be "already up to date"
            if "already up to date" not in pull_result.stdout.lower():
                result["errors"].append(f"git pull warning: {stderr}")
    except FileNotFoundError:
        return {"error": "git binary not found on PATH", "files_processed": 0}
    except subprocess.TimeoutExpired:
        return {"error": "git pull timed out after 60s", "files_processed": 0}

    # Step 2: Get current commit hash
    try:
        hash_result = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        current_commit = hash_result.stdout.strip()
        result["commit_hash"] = current_commit
    except Exception:
        current_commit = ""

    # Step 3: Find changed files since last sync
    subdirs = ["memories", "instructions", "skills", "knowledge"]
    changed_files = []

    if last_commit and current_commit and last_commit != current_commit:
        # Use git diff to find changed files
        try:
            diff_result = subprocess.run(
                ["git", "-C", repo_path, "diff", "--name-only", last_commit, current_commit],
                capture_output=True, text=True, timeout=30,
            )
            for line in diff_result.stdout.strip().split("\n"):
                line = line.strip()
                if line and line.endswith(".md"):
                    for subdir in subdirs:
                        if line.startswith(subdir + "/"):
                            changed_files.append(os.path.join(repo_path, line))
                            break
        except Exception:
            # If git diff fails, fall back to scanning all files
            changed_files = _scan_all_markdown(repo_path, subdirs)
    else:
        # No previous sync — process all files
        changed_files = _scan_all_markdown(repo_path, subdirs)

    # Step 4: Process each changed file through the markdown pipeline
    for file_path in changed_files:
        if not os.path.exists(file_path):
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            proc_result = process_markdown_document(conn, content)
            result["files_processed"] += 1

            if proc_result.get("action") == "created":
                result["records_created"] += 1
            elif proc_result.get("action") == "updated":
                result["records_updated"] += 1
        except Exception as e:
            result["errors"].append(f"{file_path}: {str(e)}")

    # Step 5: Record sync state
    crud.set_config(conn, "last_git_sync_commit", current_commit)
    crud.set_config(conn, "last_git_sync_at", result["timestamp"])

    return result


def commit_to_git(conn, markdown_content, doc_type, name, config=None):
    """
    Write a reverse-generated markdown file back to the git repo and commit.

    Args:
        conn: sqlite3.Connection
        markdown_content: str, the markdown to write
        doc_type: str, one of 'memory', 'instruction', 'skill', 'knowledge'
        name: str, filename-safe name for the document
        config: dict with git config

    Returns:
        dict with commit_hash or error
    """
    if config is None:
        config = _load_git_config(conn)

    repo_path = config.get("knowledge_git_repo", "")
    auto_commit = config.get("knowledge_git_auto_commit", "false") == "true"

    if not repo_path or not auto_commit:
        return {"skipped": True, "reason": "auto-commit disabled or repo not configured"}

    # Map doc_type to subdirectory
    subdir_map = {
        "memory": "memories",
        "instruction": "instructions",
        "skill": "skills",
        "knowledge": "knowledge",
    }
    subdir = subdir_map.get(doc_type, "knowledge")
    target_dir = os.path.join(repo_path, subdir)
    os.makedirs(target_dir, exist_ok=True)

    # Sanitize filename
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name)
    safe_name = safe_name.strip().replace(" ", "_")
    file_path = os.path.join(target_dir, f"{safe_name}.md")

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        # Git add and commit
        subprocess.run(
            ["git", "-C", repo_path, "add", file_path],
            capture_output=True, timeout=10,
        )
        commit_msg = f"agentdb: [{doc_type}] {name} (via UI)"
        subprocess.run(
            ["git", "-C", repo_path, "commit", "-m", commit_msg],
            capture_output=True, timeout=10,
        )

        hash_result = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return {"commit_hash": hash_result.stdout.strip(), "file_path": file_path}
    except Exception as e:
        return {"error": str(e)}


def get_sync_status(conn):
    """Get the current git sync status."""
    return {
        "last_commit": crud.get_config_value(conn, "last_git_sync_commit") or "",
        "last_sync_at": crud.get_config_value(conn, "last_git_sync_at") or "",
        "repo_path": crud.get_config_value(conn, "knowledge_git_repo") or "",
        "branch": crud.get_config_value(conn, "knowledge_git_branch") or "main",
        "auto_commit": crud.get_config_value(conn, "knowledge_git_auto_commit") == "true",
    }


def _load_git_config(conn):
    keys = ["knowledge_git_repo", "knowledge_git_branch",
            "knowledge_git_auto_commit", "last_git_sync_commit", "last_git_sync_at"]
    config = {}
    for key in keys:
        val = crud.get_config_value(conn, key)
        if val is not None:
            config[key] = val
    return config


def _scan_all_markdown(repo_path, subdirs):
    """Scan all markdown files in the knowledge subdirectories."""
    files = []
    for subdir in subdirs:
        dir_path = os.path.join(repo_path, subdir)
        if os.path.isdir(dir_path):
            for fname in os.listdir(dir_path):
                if fname.endswith(".md"):
                    files.append(os.path.join(dir_path, fname))
    return files
